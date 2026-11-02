"""dolarPy (https://dolar.melizeche.com/): community aggregator of USD/PYG boards.

``GET https://dolar.melizeche.com/api/1.0/`` answers::

    {"dolarpy": {"bcp": {"compra": 5908.35, "venta": 5922.67, "referencial_diario": 5944.76},
                 "maxicambios": {"compra": 5700.0, "venta": 5950.0},
                 "mydcambios": {"compra": 5770.0, "venta": 5930.0}, ...},
     "updated": "2026-10-30 20:50:24"}          # aggregator wall-clock time, America/Asuncion

One ``QuoteDraft`` per house. These are THIRD-PARTY REFERENCE numbers: ``modality="reference"``,
``channel="aggregator"``, ``kind="market_reference"``. They are never an executable price nor
the counter price of the house itself (the house adapters are), so the ranking and the graph
skip them; they exist to cross-check our own adapters and to cover houses we do not scrape.
``referencial_diario`` (BCP daily reference) is ignored: the ``bcp`` adapter owns that number.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dtparser

from ._common import as_text, error_result, finalize, payload_kind, slug
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

URL = "https://dolar.melizeche.com/api/1.0/"
RULE = (
    "dolarpy json v1 (dolarpy.<house>.compra/venta -> one reference quote per house; "
    "updated 'YYYY-MM-DD HH:MM:SS' America/Asuncion; referencial_diario ignored)"
)
_UPDATED_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M")


def _parse_updated(value: Any) -> datetime | None:
    text = str(value).strip()
    for fmt in _UPDATED_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ_ASUNCION)
        except ValueError:
            continue
    try:
        parsed = dtparser.isoparse(text)
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ_ASUNCION)


class DolarPyAdapter:
    info = AdapterInfo(
        id="dolarpy",
        name="dolarPy (agregador de referência)",
        kind="fintech",
        method="official_api",
        url=URL,
        capabilities=["aggregator", "reference_only", "usd_pyg", "buy_sell", "declared_update_ts", "json_endpoint"],
        limitations=[
            "referência de terceiro: nunca é preço executável nem cotação de balcão da casa; "
            "fica fora do ranking e do grafo",
            "só USD/PYG; sem cidade nem sucursal (city=None)",
            "'updated' é a hora do agregador (America/Asuncion), não a de cada casa; mais de 24 h vira STALE",
            "API comunitária sem contrato público; pode mudar ou sair do ar sem aviso",
        ],
        cities=[],
        currencies=["USD", "PYG"],
        poll_interval_s=900,
        allowed_domains=["dolar.melizeche.com"],
    )
    stale_after = timedelta(hours=24)

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock  # injectable so tests pin "now" for the staleness rule

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = self._clock()
        out = await http_get(URL, headers=default_headers(ACCEPT_JSON))
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        text = as_text(raw)
        if kind != "json":
            return error_result("payload is not JSON (HTML/maintenance page?)")
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        if not isinstance(data, dict):
            return error_result("JSON is not an object with a 'dolarpy' map")
        houses = data.get("dolarpy")
        if not isinstance(houses, dict) or not houses:
            return error_result("no 'dolarpy' houses in JSON (API shape changed?)")

        issues: list[str] = []
        declared: datetime | None = None
        updated = data.get("updated")
        if updated in (None, ""):
            issues.append("'updated' timestamp missing")
        else:
            declared = _parse_updated(updated)
            if declared is None:
                issues.append(f"unparsable 'updated' timestamp {updated!r}")

        quotes: list[QuoteDraft] = []
        for house, entry in houses.items():
            name = str(house).strip()
            if not isinstance(entry, dict):
                issues.append(f"{name}: entry is not an object")
                continue
            buy = positive_or_none(try_parse_decimal(entry.get("compra")))
            sell = positive_or_none(try_parse_decimal(entry.get("venta")))
            if buy is None and sell is None:
                issues.append(f"{name}: no positive compra/venta")
                continue
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base="USD", quote="PYG", buy=buy, sell=sell,
                    unit_note=f"PYG por 1 USD (agregador dolarPy, casa {name}: referência de terceiro, não executável)",
                    modality="reference", kind="market_reference", channel="aggregator", city=None,
                    branch_id=f"dolarpy-{slug(name)}", context={"aggregator": "dolarpy", "house": name},
                    declared_updated_at=declared,
                )
            )
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=self._excerpt(quotes, updated),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after, empty_message="no houses with positive prices")

    @staticmethod
    def _excerpt(quotes: list[QuoteDraft], updated: Any) -> str:
        lines = [
            f"dolarpy aggregator updated={updated!r} houses={len(quotes)} (third-party reference, never executable)"
        ]
        lines.extend(f"{(q.context or {}).get('house')} compra={q.buy} venta={q.sell}" for q in quotes)
        return "\n".join(lines)


adapter = DolarPyAdapter()
