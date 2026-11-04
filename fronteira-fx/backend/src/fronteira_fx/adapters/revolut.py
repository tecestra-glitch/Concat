"""Revolut currency converter.

The HTML converter page answers 403 to non-browser clients, but the JSON it uses
is reachable: ``GET https://www.revolut.com/api/exchange/quote?amount=100&country=BR
&fromCurrency=BRL&isRecipientAmount=false&toCurrency=USD&localeCode=pt-BR`` ->
``{"sender": {"amount", "currency"}, "recipient": {...}, "rate": {"from", "to", "rate",
"timestamp"}, "fxTooltip": "..."}``. Without ``localeCode`` it is a 400.

`fetch()` asks both directions (USD->BRL gives the house *buy* of USD, BRL->USD
the house *sell*, as 1/rate) and merges them into one USD/BRL quote. A 403 is
reported as ``AdapterStatus.BLOCKED``. Plan fees (free monthly allowance, 1 %
above it, weekend markup) are not in the response: region and availability of
the user's plan must be registered manually.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import ACCEPT_JSON, build_evidence, default_headers, http_get, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, QuoteDraft

QUOTE_URL = "https://www.revolut.com/api/exchange/quote"
PAGE_URL = "https://www.revolut.com/currency-converter/"
RULE_JSON = (
    "revolut json v1 (api/exchange/quote: rate.from/to/rate/timestamp; sell=1/rate(BRL->USD), buy=rate(USD->BRL))"
)
BLOCKED_NOTE = "Revolut blocks non-browser clients; region/availability must be registered manually"
_Q6 = Decimal("0.000001")


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except ArithmeticError:
        return None
    return d if d > 0 else None


class RevolutAdapter:
    info = AdapterInfo(
        id="revolut",
        name="Revolut",
        kind="fintech",
        method="official_api",
        integration="endpoint_interno",
        url=PAGE_URL,
        capabilities=["usd_brl", "buy_sell", "declared_update_ts", "json_endpoint"],
        limitations=[
            "região/disponibilidade da conta devem ser registradas manualmente (o quote público não sabe o plano)",
            "taxas por plano (franquia mensal, 1% acima, markup de fim de semana) não vêm na resposta",
            "página HTML devolve 403 a clientes não-navegador; só o endpoint JSON responde",
            "sem PYG: só USD/BRL",
        ],
        cities=[],
        currencies=["USD", "BRL"],
        poll_interval_s=600,
        allowed_domains=["www.revolut.com"],
    )
    stale_after = timedelta(hours=6)
    base = "USD"
    quote = "BRL"

    async def fetch(self, *, amount: str | int = 1000, country: str = "BR", locale: str = "pt-BR",
                    **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        headers = default_headers(ACCEPT_JSON, {"Accept-Language": f"{locale},pt;q=0.9,en;q=0.8", "Referer": PAGE_URL})
        legs: list[dict[str, Any]] = []
        for frm, to in ((self.base, self.quote), (self.quote, self.base)):
            out = await http_get(
                QUOTE_URL, headers=headers,
                params={"amount": str(amount), "country": country, "fromCurrency": frm,
                        "isRecipientAmount": "false", "toCurrency": to, "localeCode": locale},
            )
            if not out.ok:
                if out.blocked:
                    return AdapterResult(status=AdapterStatus.BLOCKED, quotes=[], evidence=None,
                                         message=f"{out.error}; {BLOCKED_NOTE}")
                return out.failure(self.info.id)
            try:
                legs.append(json.loads(out.text))
            except ValueError:
                return error_result(f"non-JSON quote response for {frm}->{to}")
        payload = json.dumps({"quotes": legs, "request": {"country": country, "locale": locale, "amount": str(amount)}})
        return self.parse(payload, captured_at=captured_at, url=QUOTE_URL, country=country, locale=locale)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "html":
            return AdapterResult(status=AdapterStatus.BLOCKED, quotes=[], evidence=None,
                                 message=f"HTML payload (converter page) cannot be parsed; {BLOCKED_NOTE}")
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        legs: list[dict[str, Any]]
        request: dict[str, Any] = {}
        if isinstance(data, dict) and isinstance(data.get("quotes"), list):
            legs = [q for q in data["quotes"] if isinstance(q, dict)]
            request = data.get("request") or {}
        elif isinstance(data, dict) and "rate" in data:
            legs = [data]
        else:
            return error_result("JSON without 'rate' (Revolut quote shape changed?)")
        country = str(params.get("country") or request.get("country") or "BR")
        locale = str(params.get("locale") or request.get("locale") or "pt-BR")

        buy = sell = None
        amount_base: Decimal | None = None
        declared: datetime | None = None
        issues: list[str] = []
        tooltips: list[str] = []
        for leg in legs:
            rate = leg.get("rate") if isinstance(leg.get("rate"), dict) else {}
            frm, to = str(rate.get("from") or "").upper(), str(rate.get("to") or "").upper()
            r = _dec(rate.get("rate"))
            if r is None:
                issues.append(f"leg {frm}->{to}: no rate")
                continue
            ts = rate.get("timestamp")
            if isinstance(ts, (int, float)) and ts > 0:
                when = datetime.fromtimestamp(float(ts) / 1000.0, tz=UTC)
                declared = when if declared is None or when > declared else declared
            if frm == self.base and to == self.quote:
                buy = r.quantize(_Q6, rounding=ROUND_HALF_EVEN)
                sender = leg.get("sender") or {}
                if str(sender.get("currency", "")).upper() == self.base:
                    amount_base = _dec(sender.get("amount"))
            elif frm == self.quote and to == self.base:
                sell = (Decimal(1) / r).quantize(_Q6, rounding=ROUND_HALF_EVEN)
            else:
                issues.append(f"leg {frm}->{to}: not the {self.base}/{self.quote} pair")
            if leg.get("fxTooltip"):
                tooltips.append(str(leg["fxTooltip"]))
        if buy is None and sell is None:
            return error_result("; ".join(issues) or "no usable legs")
        q = QuoteDraft(
            source_id=self.info.id, base=self.base, quote=self.quote, buy=buy, sell=sell,  # type: ignore[arg-type]
            unit_note=f"{self.quote} por 1 {self.base} (quote público Revolut; compra=USD->BRL, venda=1/(BRL->USD))",
            modality="account", kind="indicative", channel="digital", city=None, amount_base=amount_base,
            context={"country": country, "locale": locale, "plan": "unknown", "surface": "public_quote_api"},
            declared_updated_at=declared,
        )
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt([q], header="fxTooltip: " + " | ".join(dict.fromkeys(tooltips))),
        )
        if buy is None or sell is None:
            issues.append("only one direction present")
        return finalize(quotes=[q], evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = RevolutAdapter()
