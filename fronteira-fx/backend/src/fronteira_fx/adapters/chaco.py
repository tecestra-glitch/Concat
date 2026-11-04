"""Cambios Chaco (https://www.cambioschaco.com.py/).

The site is WordPress but its rate board is filled from a JSON API that the
page's own JS calls (`API_URL = https://www.cambioschaco.com.py/api`):

* ``GET /api/branch_office/``               -> list of branches (id, title, city, address...)
* ``GET /api/branch_office/{id}/exchange``  -> {"updateTs", "branchOfficeId", "items": [{isoCode,
  purchasePrice, salePrice, ...}]}   (returns ``[]`` when a branch has no data)

`fetch()` replays those requests (reproducible, no HTML scraping). `parse()`
accepts the combined JSON `{"branches": [...], "exchanges": [...]}` that fetch
assembles, a single exchange object, or, as a fallback, the home page HTML
(table ``#main-exchange-content`` for the selected branch).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dtparser
from selectolax.lexbor import LexborHTMLParser

from ._common import (
    BranchInfo,
    as_text,
    city_from_text,
    error_result,
    finalize,
    payload_kind,
    quotes_excerpt,
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
from .base import AdapterInfo, AdapterResult, AdapterStatus, QuoteDraft

BASE = "https://www.cambioschaco.com.py"
HOME_URL = f"{BASE}/"
API_BRANCHES = f"{BASE}/api/branch_office/"
API_EXCHANGE = f"{BASE}/api/branch_office/{{id}}/exchange"

CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
RULE_JSON = "chaco json v1 (api/branch_office/{id}/exchange: items[].purchasePrice/salePrice)"
RULE_HTML = "chaco html fallback v1 (#main-exchange-content tr .purchase/.sale, #update-ts)"

# Snapshot of GET /api/branch_office/ (2026-11-02). Refreshed from the live list on every fetch;
# kept here so parse() can label branches offline and tests do not depend on the network.
KNOWN_BRANCHES: dict[str, BranchInfo] = {
    b.remote_code: b
    for b in (
        BranchInfo("chaco-1", "Casa Central - Asuncion", "ASU", "1", "Mariscal López Nº 3841 c/ O´higgins"),
        BranchInfo("chaco-2", "Shopping Villa Morra - Asuncion", "ASU", "2"),
        BranchInfo("chaco-3", "Shopping Multiplaza - Asuncion", "ASU", "3"),
        BranchInfo("chaco-30", "Palma", "ASU", "30"),
        BranchInfo("chaco-6", "Agencia San Lorenzo", None, "6"),
        BranchInfo("chaco-7", "Aeropuerto Intl Silvio Pettirossi", None, "7"),
        BranchInfo("chaco-8", "Paseo Lambaré", None, "8"),
        BranchInfo("chaco-9", "Ciudad del Este - Sucursal Adrián Jara", "CDE", "9"),
        BranchInfo("chaco-11", "Ciudad del Este - Itá Ybate", "CDE", "11"),
        BranchInfo("chaco-13", "Ciudad del Este - Noblesse - KM 3,5", "CDE", "13"),
        BranchInfo("chaco-14", "Ag. Plaza Madero", None, "14"),
        BranchInfo("chaco-16", "Hernandarias - Super Carretera", None, "16"),
        BranchInfo("chaco-22", "Itaipú", None, "22"),
        BranchInfo("chaco-23", "Sucursal Super 6 - ENC", None, "23"),
        BranchInfo("chaco-24", "ENC. Mcal. Estigarribia - Zona Alta", None, "24"),
        BranchInfo("chaco-27", "Sucursal Santa Rita", None, "27"),
        BranchInfo("chaco-28", "Sucursal Pedro Juan Caballero", "PJC", "28"),
        BranchInfo("chaco-29", "Agencia Pedro Juan Caballero", "PJC", "29"),
        BranchInfo("chaco-32", "Ciudad del Este  - Km7", "CDE", "32"),
        BranchInfo("chaco-40", "Ciudad del Este - Curupayty", "CDE", "40"),
        BranchInfo("chaco-41", "Minga Guazu - Abasto Este", None, "41"),
    )
}


def _branch_from_api(entry: dict[str, Any]) -> BranchInfo | None:
    bid = str(entry.get("id") or "").strip()
    if not bid:
        return None
    title = str(entry.get("title") or f"Sucursal {bid}").strip()
    city = city_from_text(str(entry.get("city") or "")) or city_from_text(title)
    return BranchInfo(f"chaco-{bid}", title, city, bid, entry.get("address") or None)


def _parse_update_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return dtparser.isoparse(str(value))
    except (ValueError, TypeError):
        return None


class ChacoAdapter:
    info = AdapterInfo(
        id="chaco",
        name="Cambios Chaco",
        kind="exchange_house",
        method="official_api",
        integration="endpoint_interno",
        url=HOME_URL,
        capabilities=["branch_table", "buy_sell", "usd_pyg", "brl_pyg", "declared_update_ts", "json_endpoint"],
        limitations=[
            "API JSON não documentada (a mesma que o site usa); pode mudar sem aviso",
            "cotação de balcão indicativa; valor efetivo depende do montante e da filial",
            "filiais fora de CDE/ASU/PJC ficam sem cidade (city=None)",
        ],
        cities=["CDE", "ASU", "PJC"],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.cambioschaco.com.py"],
    )
    stale_after = timedelta(hours=36)
    concurrency = 4

    # ------------------------------------------------------------------ fetch
    @staticmethod
    def default_branch_ids(branches: dict[str, BranchInfo] | None = None) -> list[str]:
        table = branches or KNOWN_BRANCHES
        return [b.remote_code for b in table.values() if b.city is not None]

    async def fetch(self, *, branch_ids: list[str] | None = None, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        issues: list[str] = []
        headers = default_headers(ACCEPT_JSON, {"Referer": HOME_URL})

        branch_out = await http_get(API_BRANCHES, headers=headers)
        branch_list: list[dict[str, Any]] = []
        if branch_out.ok:
            try:
                loaded = json.loads(branch_out.text)
                branch_list = loaded if isinstance(loaded, list) else []
            except ValueError:
                issues.append("branch list is not JSON")
        elif branch_out.blocked:
            return branch_out.failure(self.info.id)
        else:
            issues.append(f"branch list: {branch_out.error}")

        branches = dict(KNOWN_BRANCHES)
        for entry in branch_list:
            info = _branch_from_api(entry) if isinstance(entry, dict) else None
            if info:
                branches[info.remote_code] = info
        wanted = [str(b) for b in branch_ids] if branch_ids else self.default_branch_ids(branches)

        sem = asyncio.Semaphore(self.concurrency)

        async def one(bid: str) -> tuple[str, Any]:
            async with sem:
                return bid, await http_get(API_EXCHANGE.format(id=bid), headers=headers)

        results = await asyncio.gather(*(one(b) for b in wanted))
        exchanges: list[dict[str, Any]] = []
        blocked = 0
        for bid, out in results:
            if not out.ok:
                blocked += int(out.blocked)
                issues.append(f"branch {bid}: {out.error}")
                continue
            try:
                data = json.loads(out.text)
            except ValueError:
                issues.append(f"branch {bid}: not JSON")
                continue
            if isinstance(data, dict):
                data.setdefault("branchOfficeId", bid)
                exchanges.append(data)
            else:
                issues.append(f"branch {bid}: empty payload ({out.text[:20]!r})")
        if results and blocked == len(results):
            return AdapterResult(status=AdapterStatus.BLOCKED, quotes=[], evidence=None,
                                 message="all branch requests blocked: " + "; ".join(issues))
        combined = {"branches": branch_list, "exchanges": exchanges}
        return self.parse(
            json.dumps(combined, ensure_ascii=False),
            captured_at=captured_at,
            url=API_EXCHANGE.format(id="{id}"),
            fetch_issues=issues,
        )

    # ------------------------------------------------------------------ parse
    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        fetch_issues: list[str] = list(params.get("fetch_issues") or [])
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "json":
            try:
                data = json.loads(text)
            except ValueError as exc:
                return error_result(f"invalid JSON: {exc}")
            return self._parse_json(data, text, captured_at=captured_at, url=url, issues=fetch_issues)
        return self._parse_html(text, captured_at=captured_at, url=url, issues=fetch_issues)

    def _parse_json(self, data: Any, text: str, *, captured_at: datetime, url: str, issues: list[str]) -> AdapterResult:
        branch_list: list[dict[str, Any]] = []
        exchanges: list[dict[str, Any]] = []
        if isinstance(data, dict) and "exchanges" in data:
            branch_list = [b for b in (data.get("branches") or []) if isinstance(b, dict)]
            exchanges = [e for e in (data.get("exchanges") or []) if isinstance(e, dict)]
        elif isinstance(data, dict) and "items" in data:
            exchanges = [data]
        elif isinstance(data, list):
            if data and all(isinstance(e, dict) and "items" in e for e in data):
                exchanges = data
            elif data and all(isinstance(e, dict) and "title" in e for e in data):
                return error_result("payload is only the branch list; no exchange data")
        if not exchanges:
            return error_result("no exchange objects in payload" + ("; " + "; ".join(issues) if issues else ""))

        branches = dict(KNOWN_BRANCHES)
        for entry in branch_list:
            info = _branch_from_api(entry)
            if info:
                branches[info.remote_code] = info

        quotes: list[QuoteDraft] = []
        for ex in exchanges:
            bid = str(ex.get("branchOfficeId") or "").strip()
            binfo = branches.get(bid) or BranchInfo(f"chaco-{bid or 'unknown'}", f"Sucursal {bid or '?'}", None, bid)
            declared = _parse_update_ts(ex.get("updateTs"))
            seen: set[str] = set()
            for item in ex.get("items") or []:
                if not isinstance(item, dict):
                    continue
                iso = str(item.get("isoCode") or "").upper()
                if iso not in CURRENCIES:
                    continue
                buy = positive_or_none(try_parse_decimal(item.get("purchasePrice")))
                sell = positive_or_none(try_parse_decimal(item.get("salePrice")))
                if buy is None and sell is None:
                    issues.append(f"branch {bid}: {iso} has no positive prices")
                    continue
                seen.add(iso)
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id,
                        base=iso,  # type: ignore[arg-type]
                        quote="PYG",
                        buy=buy,
                        sell=sell,
                        unit_note=f"PYG por 1 {iso}",
                        modality="cash",
                        kind="indicative",
                        channel="physical",
                        city=binfo.city,
                        branch_id=binfo.id,
                        declared_updated_at=declared or _parse_update_ts(item.get("updatedAt")),
                    )
                )
            for missing in sorted(CURRENCIES - seen):
                issues.append(f"branch {bid} ({binfo.name}): missing {missing}")
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt(quotes, header=f"{len(exchanges)} branch payload(s)"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _parse_html(self, text: str, *, captured_at: datetime, url: str, issues: list[str]) -> AdapterResult:
        tree = LexborHTMLParser(text)
        rows = tree.css("#main-exchange-content tr")
        if not rows:
            return error_result("rate table not found (#main-exchange-content); layout changed?")
        selected = tree.css_first("select#home_change_branch_office_id option[selected]")
        remote = (selected.attributes.get("value") or "1").strip() if selected else "1"
        binfo = KNOWN_BRANCHES.get(remote) or BranchInfo(
            f"chaco-{remote}", selected.text(strip=True) if selected else f"Sucursal {remote}", None, remote
        )
        declared: datetime | None = None
        ts_node = tree.css_first("#update-ts")
        if ts_node:
            try:
                declared = datetime.strptime(ts_node.text(strip=True), "%d/%m/%Y %H:%M").replace(tzinfo=TZ_ASUNCION)
            except ValueError:
                issues.append(f"unparsable update timestamp {ts_node.text(strip=True)!r}")
        quotes: list[QuoteDraft] = []
        for row in rows:
            row_id = row.attributes.get("id") or ""
            iso = row_id.split("-", 1)[1].upper() if "-" in row_id else ""
            if iso not in CURRENCIES:
                continue
            buy_node, sell_node = row.css_first(".purchase"), row.css_first(".sale")
            buy = positive_or_none(try_parse_decimal(buy_node.text(strip=True), "es_PY")) if buy_node else None
            sell = positive_or_none(try_parse_decimal(sell_node.text(strip=True), "es_PY")) if sell_node else None
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
        issues.append("html fallback: only the selected branch is on the page")
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = ChacoAdapter()
