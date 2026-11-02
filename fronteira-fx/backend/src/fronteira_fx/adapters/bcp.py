"""Banco Central del Paraguay, reference table
(https://www.bcp.gov.py/webapps/web/cotizacion/monedas).

Server-rendered table ``#cotizacion-interbancaria``: header "PLANILLA DE
COTIZACIONES AL <DÍA> <dd> DE <MES> DEL <yyyy>", rows ``td[0]`` name, ``td[1]``
ISO, ``td[2]`` units of the currency per USD, ``td[3]`` guaraníes per unit
(es_PY numbers: "5.944,76"). The date is also in ``input#dp_cotizacion``.

The BCP publishes ONE reference value per currency (no compra/venta), so the
quote carries ``buy == sell == reference`` and says so in ``unit_note``.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt, strip_accents
from ._http import TZ_ASUNCION, build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, QuoteDraft

URL = "https://www.bcp.gov.py/webapps/web/cotizacion/monedas"
RULE_HTML = (
    "bcp html v1 (#cotizacion-interbancaria tbody tr: td[1]=ISO, td[3]=PYG por unidade; "
    "#dp_cotizacion/header date)"
)
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_HEADER_RE = re.compile(r"AL\s+[A-Z]+\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DEL?\s+(\d{4})", re.I)


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


class BcpAdapter:
    info = AdapterInfo(
        id="bcp",
        name="Banco Central del Paraguay (referencial)",
        kind="central_bank",
        method="html",
        url=URL,
        capabilities=["market_reference", "usd_pyg", "brl_pyg", "declared_date"],
        limitations=[
            "valor referencial único por moeda (sem compra/venta): buy == sell",
            "publicado em dias úteis; fins de semana/feriados repetem a última planilha",
            "não é executável: serve só como referência de mercado",
        ],
        cities=[],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=3600,
        allowed_domains=["www.bcp.gov.py"],
    )
    stale_after = timedelta(days=4)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        out = await http_get(URL, headers=default_headers())
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        if payload_kind(raw) == "empty":
            return error_result("empty payload")
        text = as_text(raw)
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
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base=iso, quote="PYG", buy=ref, sell=ref,  # type: ignore[arg-type]
                    unit_note=f"PYG por 1 {iso} (tipo de cambio referencial BCP: valor único, sem compra/venta)",
                    modality="transfer", kind="market_reference", channel="digital", city=None,
                    declared_updated_at=declared,
                )
            )
        for missing in sorted(CURRENCIES - seen):
            issues.append(f"missing {missing}")
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE_HTML],
            excerpt_text=quotes_excerpt(quotes, header=f"planilla {declared.date().isoformat() if declared else '?'}"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = BcpAdapter()
