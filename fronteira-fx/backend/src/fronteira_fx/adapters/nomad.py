"""Nomad (https://www.nomadglobal.com/cotacao/dolar-hoje).

The public "Dólar hoje" page (Webflow) is filled client-side from
``GET https://api.benomad.us/forex-rates-s3/v1/exchanges:90-days`` (the URL is in
``<div data-nm-contexto data-api=... data-par="USD_BRL">``). The payload is
``{"history": [{"date": ISO, "rates": {"dolar_exchange": 5.4437, "isDropping": false}}, ...]}``
newest first; the page's "calculadora pública" converts with that value, which
is the *dólar comercial* (market reference) — Nomad's own spread is NOT shown on
this page, so the quote is indicative and ``buy == sell == comercial``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from dateutil import parser as dtparser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import ACCEPT_JSON, build_evidence, default_headers, http_get, utcnow
from .base import AdapterInfo, AdapterResult, QuoteDraft

PAGE_URL = "https://www.nomadglobal.com/cotacao/dolar-hoje"
API_URL = "https://api.benomad.us/forex-rates-s3/v1/exchanges:90-days"
RULE_JSON = "nomad json v1 (api.benomad.us exchanges:90-days -> history[newest].rates.*_exchange)"
_DATA_API_RE = re.compile(r'data-api="([^"]+)"')


def api_url_from_html(text: str) -> str | None:
    m = _DATA_API_RE.search(text)
    return m.group(1) if m else None


def _rate_of(rates: Any) -> Decimal | None:
    if not isinstance(rates, dict):
        return None
    value = rates.get("exchange")
    if value is None:
        for key, v in rates.items():
            if str(key).endswith("_exchange"):
                value = v
                break
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value))
    except ArithmeticError:
        return None
    return d if d > 0 else None


class NomadAdapter:
    info = AdapterInfo(
        id="nomad",
        name="Nomad",
        kind="fintech",
        method="official_api",
        integration="endpoint_interno",
        url=PAGE_URL,
        capabilities=["usd_brl", "indicative", "declared_update_ts", "history_90d", "json_endpoint"],
        limitations=[
            "proposta efetiva depende da conta: a página pública mostra o dólar comercial, sem o spread da Nomad",
            "spread % não exibido na página (registrar manualmente nas taxas da conta)",
            "endpoint api.benomad.us não documentado; pode mudar sem aviso",
            "sem PYG: só USD/BRL",
        ],
        cities=[],
        currencies=["USD", "BRL"],
        poll_interval_s=600,
        allowed_domains=["www.nomadglobal.com", "api.benomad.us"],
    )
    stale_after = timedelta(hours=36)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        out = await http_get(API_URL, headers=default_headers(ACCEPT_JSON, {"Origin": "https://www.nomadglobal.com",
                                                                              "Referer": PAGE_URL}))
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "html":
            api = api_url_from_html(text)
            return error_result(f"page is JS-rendered; parse() needs the JSON from {api or API_URL}")
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        history = data.get("history") if isinstance(data, dict) else None
        if not isinstance(history, list) or not history:
            return error_result("JSON without 'history' entries; API changed?")
        entries: list[tuple[datetime, Decimal, dict[str, Any]]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            rate = _rate_of(item.get("rates"))
            try:
                when = dtparser.isoparse(str(item.get("date")))
            except (ValueError, TypeError):
                continue
            if rate is not None:
                entries.append((when, rate, item))
        if not entries:
            return error_result("no usable rate in history")
        entries.sort(key=lambda e: e[0], reverse=True)
        when, rate, item = entries[0]
        quote = QuoteDraft(
            source_id=self.info.id, base="USD", quote="BRL", buy=rate, sell=rate,
            unit_note=("BRL por 1 USD (dólar comercial exibido pela calculadora pública da Nomad; "
                       "spread da conta não incluído)"),
            modality="account", kind="indicative", channel="digital", city=None,
            context={"rate_type": "comercial", "surface": "calculadora_publica", "pair": "USD_BRL"},
            declared_updated_at=when,
        )
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt([quote], header=f"newest of {len(entries)} entries; raw={json.dumps(item)}"),
        )
        return finalize(quotes=[quote], evidence=evidence, issues=[], captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = NomadAdapter()
