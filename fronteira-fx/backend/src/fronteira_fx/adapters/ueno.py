"""ueno bank (https://www.ueno.com.py/cambio-de-moneda/).

WordPress page with one card per currency *and* modality::

    <div class="divisas-card" data-currency="USD" data-subtitle="en tu app"> ... <span>Compra</span>
    <span>Gs. 5.720</span> ... <span>Venta</span><span>Gs. 6.050</span>

Subtitles: "en tu app" (digital account), "en efectivo" (cash at branches),
"en transferencias" (digital transfer). The page's JS refreshes the cards with
``POST wp-admin/admin-ajax.php`` (``action=get_fresh_currency_data&nonce=<page nonce>``)
which answers ``{"success": true, "data": {"cards": [{currency, subtitle, compra, venta,
last_updated}], "last_updated": <epoch>}}``. `fetch()` reads the page, then tries that
AJAX call for fresh values + declared time, falling back to the page cards.

Only USD and BRL are mapped (EUR is outside the terminal's currencies). As of
2026-11 the public page publishes USD and EUR only: a missing BRL is reported as
a note, not as degradation.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import (
    ACCEPT_JSON,
    build_evidence,
    default_headers,
    http_get,
    http_post,
    positive_or_none,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, Channel, Modality, QuoteDraft

URL = "https://www.ueno.com.py/cambio-de-moneda/"
AJAX_URL = "https://www.ueno.com.py/wp-admin/admin-ajax.php"
AJAX_ACTION = "get_fresh_currency_data"
RULE_HTML = "ueno html v1 (.divisas-card[data-currency][data-subtitle] spans Compra/Venta 'Gs. 5.680')"
RULE_JSON = "ueno ajax v1 (admin-ajax get_fresh_currency_data -> data.cards[].compra/venta, last_updated)"

CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
MODALITIES: dict[str, tuple[Modality, Channel]] = {
    "en tu app": ("account", "digital"),
    "en efectivo": ("cash", "physical"),
    "en transferencias": ("transfer", "digital"),
}
_NONCE_RE = re.compile(r"formData\.append\(\s*['\"]nonce['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)")


def _join(*parts: str | None) -> str:
    return "; ".join(p for p in parts if p)


def nonce_from_html(text: str) -> str | None:
    m = _NONCE_RE.search(text)
    return m.group(1) if m else None


class UenoAdapter:
    info = AdapterInfo(
        id="ueno",
        name="ueno",
        kind="bank",
        method="html",
        integration="html",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "modalities_app_cash_transfer", "ajax_refresh", "declared_update_ts"],
        limitations=[
            "canal digital sem cidade (city=None); 'en efectivo' é balcão sem filial identificada",
            "BRL não publicado na página pública em 2026-11 (só USD/EUR): BRL/PYG indisponível",
            "cotação indicativa; a conversão efetiva no app pode diferir por conta/limite",
        ],
        cities=[],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.ueno.com.py"],
        discontinued=True,  # resolução pelo Banco Central del Paraguay em 03/11/2026: só histórico
    )
    stale_after = timedelta(hours=36)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        page = await http_get(URL, headers=default_headers())
        if not page.ok:
            return page.failure(self.info.id)
        page_result = self.parse(page.text, captured_at=captured_at, url=page.url)
        nonce = nonce_from_html(page.text)
        if not nonce:
            page_result.message = _join(page_result.message, "ajax nonce not found; page cards only")
            return page_result
        ajax = await http_post(
            AJAX_URL,
            data={"action": AJAX_ACTION, "nonce": nonce},
            headers=default_headers(ACCEPT_JSON, {"Referer": URL, "Origin": "https://www.ueno.com.py",
                                                  "X-Requested-With": "XMLHttpRequest"}),
        )
        if ajax.ok:
            fresh = self.parse(ajax.text, captured_at=captured_at, url=AJAX_URL)
            if fresh.quotes:
                return fresh
            page_result.message = _join(page_result.message, f"ajax refresh unusable: {fresh.message}")
        else:
            page_result.message = _join(page_result.message, f"ajax refresh failed: {ajax.error}")
        return page_result

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "json":
            return self._parse_json(text, captured_at=captured_at, url=url)
        return self._parse_html(text, captured_at=captured_at, url=url)

    def _quote(self, iso: str, subtitle: str, buy: Any, sell: Any, declared: datetime | None,
               issues: list[str], locale: str) -> QuoteDraft | None:
        modality = MODALITIES.get(subtitle.strip().lower())
        if modality is None:
            issues.append(f"{iso}: unknown modality {subtitle!r}")
            return None
        b = positive_or_none(try_parse_decimal(buy, locale))  # type: ignore[arg-type]
        s = positive_or_none(try_parse_decimal(sell, locale))  # type: ignore[arg-type]
        if b is None and s is None:
            issues.append(f"{iso} {subtitle}: no prices")
            return None
        return QuoteDraft(
            source_id=self.info.id, base=iso, quote="PYG", buy=b, sell=s,  # type: ignore[arg-type]
            unit_note=f"PYG por 1 {iso}", modality=modality[0], kind="indicative", channel=modality[1],
            city=None, context={"ueno_card": subtitle.strip().lower()}, declared_updated_at=declared,
        )

    def _finish(self, quotes: list[QuoteDraft], seen: set[str], issues: list[str], *, text: str, url: str,
                captured_at: datetime, kind: str, rule: str) -> AdapterResult:
        notes = [f"{c} not published on the page" for c in sorted(CURRENCIES - seen)]
        if "USD" not in seen:
            issues.append("USD cards missing")
        evidence = build_evidence(
            source_id=self.info.id, kind=kind, url=url, captured_at=captured_at, raw=text, rules=[rule],  # type: ignore[arg-type]
            excerpt_text=quotes_excerpt(quotes, header=f"ueno {kind} cards"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _parse_json(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        payload = data.get("data") if isinstance(data, dict) else None
        cards = payload.get("cards") if isinstance(payload, dict) else None
        if not isinstance(cards, list) or not cards:
            return error_result("ajax JSON without data.cards")
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for card in cards:
            if not isinstance(card, dict):
                continue
            iso = str(card.get("currency") or "").upper()
            if iso not in CURRENCIES:
                continue
            declared: datetime | None = None
            epoch = card.get("last_updated") or payload.get("last_updated")
            if isinstance(epoch, (int, float)) and epoch > 0:
                declared = datetime.fromtimestamp(float(epoch), tz=UTC)
            q = self._quote(iso, str(card.get("subtitle") or ""), card.get("compra"), card.get("venta"), declared,
                            issues, "es_PY")
            if q:
                seen.add(iso)
                quotes.append(q)
        return self._finish(quotes, seen, issues, text=text, url=url, captured_at=captured_at, kind="json",
                            rule=RULE_JSON)

    def _parse_html(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        tree = LexborHTMLParser(text)
        cards = tree.css(".divisas-card[data-currency][data-subtitle]")
        if not cards:
            return error_result("no .divisas-card elements; layout changed?")
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for card in cards:
            iso = (card.attributes.get("data-currency") or "").strip().upper()
            subtitle = (card.attributes.get("data-subtitle") or "").strip()
            if iso not in CURRENCIES:
                continue
            values: dict[str, str] = {}
            spans = [s.text(strip=True) for s in card.css("span")]
            for label, value in zip(spans, spans[1:], strict=False):
                key = label.lower()
                if key in ("compra", "venta") and key not in values:
                    values[key] = value
            q = self._quote(iso, subtitle, values.get("compra"), values.get("venta"), None, issues, "es_PY")
            if q:
                seen.add(iso)
                quotes.append(q)
        return self._finish(quotes, seen, issues, text=text, url=url, captured_at=captured_at, kind="html",
                            rule=RULE_HTML)


adapter = UenoAdapter()
