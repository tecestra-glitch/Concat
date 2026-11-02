"""Banco Central del Paraguay reference rates (``kind=market_reference``).

Primary source: Frankfurter republishes the BCP table as JSON, no key needed::

    GET https://api.frankfurter.dev/v2/providers/bcp/rates?base=USD&quotes=PYG
    -> [{"date": "2026-10-30", "base": "USD", "quote": "PYG", "rate": 5944.76}]
    GET ...?base=BRL&quotes=PYG  -> [{"date": "2026-10-30", "base": "BRL", "quote": "PYG", "rate": 1100.01}]

(the parameter is ``quotes``, not ``symbols``). ``declared_updated_at`` is the ``date``.

Fallback: the BCP page https://www.bcp.gov.py/webapps/web/cotizacion/monedas, a
server-rendered table ``#cotizacion-interbancaria`` with header "PLANILLA DE
COTIZACIONES AL <DÍA> <dd> DE <MES> DEL <yyyy>" and rows ``td[0]`` name, ``td[1]``
ISO, ``td[2]`` units of the currency per USD, ``td[3]`` guaraníes per unit
(es_PY numbers: "5.944,76"; USD/PYG is ~5,945 — ``td[2]`` is NOT the PYG price).
The date is also in ``input#dp_cotizacion``.

The BCP publishes ONE reference value per currency (no compra/venta), so quotes
carry ``buy == sell == reference`` and say so in ``unit_note``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt, strip_accents
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
from .base import AdapterInfo, AdapterResult, AdapterStatus, QuoteDraft

URL = "https://www.bcp.gov.py/webapps/web/cotizacion/monedas"
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/providers/bcp/rates"
RULE_JSON = (
    "bcp frankfurter v1 (v2/providers/bcp/rates: [{date, base, quote, rate}]; BRL/PYG derived from USD cross if absent)"
)
RULE_HTML = (
    "bcp html v1 (#cotizacion-interbancaria tbody tr: td[1]=ISO, td[3]=PYG por unidade; "
    "#dp_cotizacion/header date)"
)
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
PAIRS: tuple[tuple[str, str], ...] = (("USD", "PYG"), ("BRL", "PYG"))

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_HEADER_RE = re.compile(r"AL\s+[A-Z]+\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DEL?\s+(\d{4})", re.I)
_Q2 = Decimal("0.01")


def _join(*parts: str | None) -> str | None:
    return "; ".join(p for p in parts if p) or None


def _declared_date(tree: LexborHTMLParser, text: str) -> datetime | None:
    node = tree.css_first("input#dp_cotizacion")
    value = (node.attributes.get("value") or "").strip() if node else ""
    if value:
        try:
            return datetime.strptime(value, "%d/%m/%Y").replace(tzinfo=TZ_ASUNCION)
        except ValueError:
            pass
    header = tree.css_first("#cotizacion-interbancaria thead") or tree.css_first("thead")
    m = _HEADER_RE.search(strip_accents(header.text()) if header else strip_accents(text))
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = _MONTHS.get(month_name)
        if month:
            try:
                return datetime(year, month, day, tzinfo=TZ_ASUNCION)
            except ValueError:
                return None
    return None


def _iso_date(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=TZ_ASUNCION)
    except (ValueError, TypeError):
        return None


class BcpAdapter:
    info = AdapterInfo(
        id="bcp",
        name="Banco Central del Paraguay (referencial)",
        kind="central_bank",
        method="official_api",
        url=URL,
        capabilities=["market_reference", "usd_pyg", "brl_pyg", "declared_date", "json_feed", "html_fallback"],
        limitations=[
            "valor referencial único por moeda (sem compra/venta): buy == sell",
            "publicado em dias úteis; fins de semana/feriados repetem a última planilha",
            "não é executável: serve só como referência de mercado",
            "feed JSON é um espelho (Frankfurter) da planilha do BCP; se falhar, cai para o HTML do bcp.gov.py",
        ],
        cities=[],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=3600,
        allowed_domains=["api.frankfurter.dev", "www.bcp.gov.py"],
    )
    stale_after = timedelta(days=4)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        entries: list[dict[str, Any]] = []
        issues: list[str] = []
        for base, quote in PAIRS:
            out = await http_get(FRANKFURTER_URL, params={"base": base, "quotes": quote},
                                 headers=default_headers(ACCEPT_JSON))
            if not out.ok:
                issues.append(f"frankfurter {base}->{quote}: {out.error}")
                continue
            try:
                data = json.loads(out.text)
            except ValueError:
                issues.append(f"frankfurter {base}->{quote}: not JSON")
                continue
            if isinstance(data, list):
                entries.extend(d for d in data if isinstance(d, dict))
            else:
                issues.append(f"frankfurter {base}->{quote}: unexpected JSON shape")
        if entries:
            res = self.parse(json.dumps(entries), captured_at=captured_at, url=FRANKFURTER_URL)
            if res.status != AdapterStatus.ERROR:
                res.message = _join(res.message, *issues)
                return res
            issues.append(f"frankfurter payload unusable: {res.message}")

        page = await http_get(URL, headers=default_headers())
        if not page.ok:
            failure = page.failure(self.info.id)
            failure.message = _join("; ".join(issues) or None, f"bcp.gov.py: {failure.message}")
            return failure
        res = self.parse(page.text, captured_at=captured_at, url=page.url)
        res.message = _join(res.message, "html fallback (" + "; ".join(issues) + ")")
        return res

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        text = as_text(raw)
        if kind == "json":
            return self._parse_json(text, captured_at=captured_at, url=url)
        return self._parse_html(text, captured_at=captured_at, url=url)

    def _quote(self, iso: str, ref: Decimal, declared: datetime | None, note: str = "") -> QuoteDraft:
        return QuoteDraft(
            source_id=self.info.id, base=iso, quote="PYG", buy=ref, sell=ref,  # type: ignore[arg-type]
            unit_note=f"PYG por 1 {iso} (tipo de cambio referencial BCP: valor único, sem compra/venta){note}",
            modality="transfer", kind="market_reference", channel="digital", city=None,
            declared_updated_at=declared,
        )

    def _parse_json(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        if isinstance(data, dict):
            data = data.get("rates") if isinstance(data.get("rates"), list) else [data]
        if not isinstance(data, list):
            return error_result("JSON is not a list of {date, base, quote, rate}")
        rates: dict[tuple[str, str], tuple[Decimal, datetime | None]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            base, quote = str(item.get("base") or "").upper(), str(item.get("quote") or "").upper()
            rate = positive_or_none(try_parse_decimal(item.get("rate")))
            if base and quote and rate is not None:
                rates[(base, quote)] = (rate, _iso_date(item.get("date")))
        if not rates:
            return error_result("no usable rate entries in JSON (Frankfurter shape changed?)")
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        usd = rates.get(("USD", "PYG"))
        if usd:
            quotes.append(self._quote("USD", usd[0], usd[1]))
        else:
            issues.append("missing USD")
        brl = rates.get(("BRL", "PYG"))
        if brl:
            quotes.append(self._quote("BRL", brl[0], brl[1]))
        elif usd and rates.get(("USD", "BRL")):
            cross = rates[("USD", "BRL")]
            derived = (usd[0] / cross[0]).quantize(_Q2, rounding=ROUND_HALF_EVEN)
            quotes.append(self._quote("BRL", derived, cross[1] or usd[1], " [derivado: USD/PYG ÷ USD/BRL]"))
        else:
            issues.append("missing BRL")
        declared = next((q.declared_updated_at for q in quotes if q.declared_updated_at), None)
        if declared is None and quotes:
            issues.append("declared date not found")
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt(quotes, header=f"frankfurter bcp {declared.date().isoformat() if declared else '?'}"
                                        ),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _parse_html(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        tree = LexborHTMLParser(text)
        table = tree.css_first("#cotizacion-interbancaria") or tree.css_first("table")
        rows = table.css("tbody tr") if table else []
        if not rows:
            return error_result("reference table not found (#cotizacion-interbancaria); layout changed?")
        declared = _declared_date(tree, text)
        issues: list[str] = []
        if declared is None:
            issues.append("declared date not found")
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for tr in rows:
            cells = tr.css("td")
            if len(cells) < 4:
                continue
            iso = cells[1].text(strip=True).upper()
            if iso not in CURRENCIES:
                continue
            ref = positive_or_none(try_parse_decimal(cells[3].text(strip=True), "es_PY"))
            if ref is None:
                issues.append(f"{iso}: unparsable reference {cells[3].text(strip=True)!r}")
                continue
            seen.add(iso)
            quotes.append(self._quote(iso, ref, declared))
        for missing in sorted(CURRENCIES - seen):
            issues.append(f"missing {missing}")
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE_HTML],
            excerpt_text=quotes_excerpt(quotes, header=f"planilla {declared.date().isoformat() if declared else '?'}"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = BcpAdapter()
