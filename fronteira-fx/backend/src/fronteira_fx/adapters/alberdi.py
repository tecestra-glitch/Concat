"""Cambios Alberdi (https://www.cambiosalberdi.com/).

The site's `assets/js/api.js` loads one JSON document with every branch:
``GET https://www.cambiosalberdi.com/ws/getTablero.json.php`` ->
``{"villamorra": [{id, bcp, moneda, compra, venta}, ...], "ciudaddeleste": [...], ...}``.
Each list ends with an ``{"id": "timer", "compra": "dd/mm/yyyy", "venta": "HH:MM:SS"}``
entry: the declared update time (America/Asuncion). Numbers are es_PY strings
("5.800" = 5800, "3,55" = 3.55). Rows whose ``bcp`` contains "->" are cross
rates (USD->BRL) and "Cheque" rows are cheques: both skipped.

`parse()` also accepts the home page HTML as a fallback (table of the branch
selected by ``?suc=``; default villamorra).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import (
    BranchInfo,
    as_text,
    error_result,
    finalize,
    payload_kind,
    quotes_excerpt,
    strip_accents,
)
from ._http import (
    ACCEPT_JSON,
    TZ_ASUNCION,
    build_evidence,
    default_headers,
    http_get,
    positive_or_none,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, QuoteDraft

BASE = "https://www.cambiosalberdi.com"
HOME_URL = f"{BASE}/"
WS_URL = f"{BASE}/ws/getTablero.json.php"

RULE_JSON = "alberdi json v1 (ws/getTablero.json.php: <branch>[].bcp/compra/venta, timer=declared)"
RULE_HTML = "alberdi html fallback v1 (.exchange-table tbody tr, .convert-tablist a.active?suc=)"

BRANCHES: dict[str, BranchInfo] = {
    "villamorra": BranchInfo("alberdi-villamorra", "Villa Morra - Asunción", "ASU", "villamorra"),
    "ciudaddeleste": BranchInfo("alberdi-ciudaddeleste", "Ciudad del Este", "CDE", "ciudaddeleste"),
    "km4": BranchInfo("alberdi-km4", "KM4 - Ciudad del Este", "CDE", "km4"),
    "saltodelguaira": BranchInfo("alberdi-saltodelguaira", "Salto del Guairá", None, "saltodelguaira"),
    "encarnacion": BranchInfo("alberdi-encarnacion", "Encarnación", "ENC", "encarnacion"),
}
# Branches whose missing USD/BRL rows are reported as an issue (the others are frontier towns
# that legitimately publish a shorter board).
TRACKED_BRANCHES: tuple[str, ...] = ("villamorra", "ciudaddeleste", "km4")

CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
_NAME_TO_ISO = {"dolar americano": "USD", "real brasileno": "BRL"}
_UPDATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})")


def _declared(date_text: str, time_text: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_text.strip()} {time_text.strip()}", "%d/%m/%Y %H:%M:%S").replace(
            tzinfo=TZ_ASUNCION
        )
    except ValueError:
        return None


def _branch(key: str) -> BranchInfo:
    return BRANCHES.get(key) or BranchInfo(f"alberdi-{key}", key, None, key)


class AlberdiAdapter:
    # The board is one JSON document (WS_URL), not the home page in `info.url`: scheduled polls GET it with
    # If-None-Match / If-Modified-Since so an unchanged board is a 304 and is not parsed again.
    conditional_get = True
    conditional_url = WS_URL
    conditional_headers = {"Accept": ACCEPT_JSON, "Referer": HOME_URL}

    info = AdapterInfo(
        id="alberdi",
        name="Cambios Alberdi",
        kind="exchange_house",
        method="official_api",
        url=HOME_URL,
        capabilities=["branch_table", "buy_sell", "usd_pyg", "brl_pyg", "declared_update_ts", "json_endpoint"],
        limitations=[
            "endpoint JSON não documentado (ws/getTablero.json.php); pode mudar sem aviso",
            "cotação de balcão indicativa; valor efetivo depende do montante e da filial",
            "Salto del Guairá fica sem cidade (city=None)",
        ],
        cities=["ASU", "CDE", "ENC"],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.cambiosalberdi.com"],
    )
    stale_after = timedelta(hours=36)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        out = await http_get(WS_URL, headers=default_headers(ACCEPT_JSON, {"Referer": HOME_URL}))
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "json":
            try:
                data = json.loads(text)
            except ValueError as exc:
                return error_result(f"invalid JSON: {exc}")
            return self._parse_json(data, text, captured_at=captured_at, url=url)
        return self._parse_html(text, captured_at=captured_at, url=url)

    def _parse_json(self, data: Any, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        if not isinstance(data, dict) or not data:
            return error_result("payload is not a branch map")
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        for key, rows in data.items():
            if not isinstance(rows, list):
                continue
            binfo = _branch(str(key))
            declared: datetime | None = None
            for row in rows:
                if isinstance(row, dict) and row.get("id") == "timer":
                    declared = _declared(str(row.get("compra") or ""), str(row.get("venta") or ""))
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, dict) or row.get("id") == "timer":
                    continue
                bcp = str(row.get("bcp") or "").strip()
                moneda = str(row.get("moneda") or "")
                if bcp == "USD -> BRL" and "cheque" not in moneda.lower():
                    # cruzamento publicado pela casa: BRL por 1 USD (compra = a casa paga, venda = cobra)
                    x_buy = positive_or_none(try_parse_decimal(row.get("compra"), "es_PY"))
                    x_sell = positive_or_none(try_parse_decimal(row.get("venta"), "es_PY"))
                    if x_buy is None and x_sell is None:
                        pass  # cruzamento zerado: a casa não opera esse par nesta filial
                    elif x_buy is None or x_sell is None:
                        issues.append(f"{key}: cruzamento USD->BRL incompleto")
                    else:
                        quotes.append(
                            QuoteDraft(
                                source_id=self.info.id, base="USD", quote="BRL", buy=x_buy, sell=x_sell,
                                unit_note="BRL por 1 USD (cruzado Dólar x Real)", modality="cash",
                                kind="indicative", channel="physical", city=binfo.city, branch_id=binfo.id,
                                context={"board": "cruzado", "pair": "USD x BRL"}, declared_updated_at=declared,
                            )
                        )
                    continue
                if "->" in bcp or "cheque" in moneda.lower() or bcp not in CURRENCIES:
                    continue
                buy = positive_or_none(try_parse_decimal(row.get("compra"), "es_PY"))
                sell = positive_or_none(try_parse_decimal(row.get("venta"), "es_PY"))
                if buy is None and sell is None:
                    continue
                seen.add(bcp)
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id, base=bcp, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                        unit_note=f"PYG por 1 {bcp}", modality="cash", kind="indicative", channel="physical",
                        city=binfo.city, branch_id=binfo.id, declared_updated_at=declared,
                    )
                )
            if key in TRACKED_BRANCHES:
                for missing in sorted(CURRENCIES - seen):
                    issues.append(f"{key}: missing {missing}")
        for key in TRACKED_BRANCHES:
            if key not in data:
                issues.append(f"{key}: branch absent from payload")
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt(quotes, header=f"branches: {', '.join(map(str, data.keys()))}"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _parse_html(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        tree = LexborHTMLParser(text)
        rows = tree.css(".exchange-table table tbody tr")
        if not rows:
            return error_result("rate table not found (.exchange-table); layout changed?")
        key = "villamorra"
        active = tree.css_first(".convert-tablist a.active")
        if active:
            m = re.search(r"suc=([a-z0-9]+)", active.attributes.get("href") or "")
            if m:
                key = m.group(1)
        binfo = _branch(key)
        declared: datetime | None = None
        m = _UPDATE_RE.search(tree.body.text() if tree.body else text)
        if m:
            declared = _declared(m.group(1), m.group(2))
        issues: list[str] = ["html fallback: only the selected branch is on the page"]
        quotes: list[QuoteDraft] = []
        for row in rows:
            cells = row.css("td")
            if len(cells) < 3:
                continue
            name = strip_accents(cells[0].text(strip=True)).lower()
            if " x " in name or "cheque" in name:
                continue
            iso = _NAME_TO_ISO.get(name)
            if iso is None:
                continue
            buy = positive_or_none(try_parse_decimal(cells[1].text(strip=True), "es_PY"))
            sell = positive_or_none(try_parse_decimal(cells[2].text(strip=True), "es_PY"))
            if buy is None and sell is None:
                issues.append(f"{iso}: no prices in row")
                continue
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base=iso, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                    unit_note=f"PYG por 1 {iso}", modality="cash", kind="indicative", channel="physical",
                    city=binfo.city, branch_id=binfo.id, declared_updated_at=declared,
                )
            )
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE_HTML],
            excerpt_text=quotes_excerpt(quotes, header=f"html fallback, branch {binfo.name}"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = AlberdiAdapter()
