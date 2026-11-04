"""Banco GNB (https://www.bancognb.com.py/), "Cotizaciones" table.

The table on the home page is filled by ``js/coronita/currencyQuotations.js``, which calls a public JSON endpoint::

    GET https://www.bancognb.com.py/public/currency_quotations
    {"exchangeRates": [{"currencyCode": "USD", "electronicBuyPrice": "5910.00", "electronicSellPrice": "6230.00",
                        "cashBuyPrice": "5890.00", "cashSellPrice": "6250.00", ...}, {"currencyCode": "EUR", ...}]}

Read here: USD on the "Home Banking" (electronic) prices, channel digital, modality account, city None.
The "Efectivo" (cash) prices are the bank's branch counter with no city in the feed, so they are not emitted
(noted). EUR is outside the terminal's currency set. The feed has no BRL and no timestamp.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

URL = "https://www.bancognb.com.py/public/currency_quotations"
RULE = "gnb json v1 (exchangeRates[currencyCode=USD] electronicBuyPrice/electronicSellPrice; PYG por 1 USD)"


class GnbAdapter:
    info = AdapterInfo(
        id="gnb",
        name="Banco GNB",
        kind="bank",
        method="official_api",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "channel_digital"],
        limitations=[
            "só USD, preço de home banking (eletrônico); o efectivo de sucursal não tem cidade e não é emitido",
            "sem BRL no feed; EUR fora do conjunto de moedas do terminal",
            "feed sem horário declarado: a idade vem do hash do conteúdo",
            "endpoint público usado pela própria página (sem chave); não é API documentada",
        ],
        cities=[],
        currencies=["USD", "PYG"],
        poll_interval_s=900,
        allowed_domains=["www.bancognb.com.py"],
    )
    stale_after = timedelta(hours=72)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        headers = default_headers(accept="application/json, text/plain, */*",
                                  extra={"X-Requested-With": "XMLHttpRequest"})
        page = await http_get(URL, headers=headers)
        if not page.ok:
            return page.failure(self.info.id)
        return self.parse(page.text, captured_at=captured_at, url=page.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind != "json":
            return error_result("HTML payload; expected the currency_quotations JSON")
        text = as_text(raw)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return error_result(f"invalid JSON: {exc}")
        rows = payload.get("exchangeRates") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            return error_result("exchangeRates empty or missing")
        quotes: list[QuoteDraft] = []
        issues: list[str] = []
        notes: list[str] = []
        usd_row = next((r for r in rows if isinstance(r, dict) and r.get("currencyCode") == "USD"), None)
        if usd_row is None:
            issues.append("USD row missing")
        else:
            buy = positive_or_none(try_parse_decimal(usd_row.get("electronicBuyPrice"), "en_US"))
            sell = positive_or_none(try_parse_decimal(usd_row.get("electronicSellPrice"), "en_US"))
            if buy is None or sell is None:
                issues.append("USD electronic buy/sell missing or zero")
            else:
                if buy > sell:
                    issues.append(f"USD: compra {buy} > venta {sell}; labels may be inverted")
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id, base="USD", quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                        unit_note="PYG por 1 USD", modality="account", kind="indicative", channel="digital",
                        city=None, branch_id=None, context={"channel": "home_banking"},
                    )
                )
        notes.append("efectivo (cash counter) prices not emitted: no city in feed; BRL not published")
        evidence = self._evidence(text, url, captured_at, quotes)
        if not quotes:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence,
                                 message="; ".join(issues) or "no quotes parsed")
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _evidence(self, text: str, url: str, captured_at: datetime, quotes: list[QuoteDraft]) -> EvidenceDraft:
        return build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=quotes_excerpt(quotes, header="gnb currency_quotations (home banking)"),
        )


adapter = GnbAdapter()
