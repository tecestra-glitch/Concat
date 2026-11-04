"""Banco Familiar (https://www.familiar.com.py/cambios), "Soluciones rápidas para la compra y venta de monedas".

Server-rendered (Webflow). Each product is a ``div.collection-item`` card::

    <div role="listitem" class="collection-item w-dyn-item">
      ... <div class="heading-s">Dólar Americano Cheque / Transf.</div>
      <div class="text-xl">Compra</div><div class="text-xl">5910</div>
      <div class="text-xl">Venta</div><div class="text-xl">6250</div>

Read here: only "Dólar Americano Cheque / Transf." (USD, transfer/cheque, digital). The "Efectivo" cards are the
branch counter with no city in the page, so they are not emitted. The "Real" card has no modality label, so it is
noted and not emitted (never guessed). Euro and Argentine peso cards are outside the terminal's currency set.
The page has no timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

URL = "https://www.familiar.com.py/cambios"
RULE = (
    "familiar html v1 (div.collection-item > .heading-s 'Dólar Americano Cheque / Transf.' -> USD; "
    ".text-xl pairs Compra/Venta; PYG por 1 USD)"
)
USD_LABEL = "Dólar Americano Cheque / Transf."
CARD = "div.collection-item"


def _card_prices(card: LexborNode) -> tuple[str | None, str | None]:
    texts = [t.text(strip=True) for t in card.css(".text-xl")]
    buy = sell = None
    for i in range(0, len(texts) - 1, 2):
        key = texts[i].lower()
        if key == "compra" and buy is None:
            buy = texts[i + 1]
        elif key == "venta" and sell is None:
            sell = texts[i + 1]
    return buy, sell


class FamiliarAdapter:
    info = AdapterInfo(
        id="familiar",
        name="Banco Familiar",
        kind="bank",
        method="html",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "channel_digital", "transfer_cheque"],
        limitations=[
            "só USD por cheque/transferência; os cards 'Efectivo' (sucursal) não têm cidade e não são emitidos",
            "card 'Real' sem modalidade rotulada: noticiado, não emitido",
            "sem horário declarado na página: a idade vem do hash do conteúdo",
            "euro e peso argentino fora do conjunto de moedas do terminal",
        ],
        cities=[],
        currencies=["USD", "PYG"],
        poll_interval_s=900,
        allowed_domains=["www.familiar.com.py"],
    )
    stale_after = timedelta(hours=72)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        page = await http_get(URL, headers=default_headers())
        if not page.ok:
            return page.failure(self.info.id)
        return self.parse(page.text, captured_at=captured_at, url=page.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "json":
            return error_result("JSON payload; expected the HTML cambios page")
        text = as_text(raw)
        tree = LexborHTMLParser(text)
        cards = tree.css(CARD)
        if not cards:
            return error_result("no product cards found (layout changed?)")
        quotes: list[QuoteDraft] = []
        issues: list[str] = []
        notes: list[str] = []
        usd_found = False
        for card in cards:
            heading = card.css_first(".heading-s")
            label = heading.text(strip=True) if heading else ""
            if label == USD_LABEL:
                usd_found = True
                buy_t, sell_t = _card_prices(card)
                buy = positive_or_none(try_parse_decimal(buy_t, "es_PY")) if buy_t else None
                sell = positive_or_none(try_parse_decimal(sell_t, "es_PY")) if sell_t else None
                if buy is None or sell is None:
                    issues.append(f"{label!r}: missing positive buy/sell")
                    continue
                if buy > sell:
                    issues.append(f"USD: compra {buy} > venta {sell}; labels may be inverted")
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id, base="USD", quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                        unit_note="PYG por 1 USD", modality="transfer", kind="indicative", channel="digital",
                        city=None, branch_id=None, context={"product": "cheque_transferencia"},
                    )
                )
            elif label == "Real":
                notes.append("card 'Real' without modality label not emitted")
        if not usd_found:
            issues.append(f"card {USD_LABEL!r} not found")
        evidence = self._evidence(text, url, captured_at, quotes)
        if not quotes:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence,
                                 message="; ".join(issues) or "no quotes parsed (layout changed?)")
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _evidence(self, text: str, url: str, captured_at: datetime, quotes: list[QuoteDraft]) -> EvidenceDraft:
        return build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=quotes_excerpt(quotes, header="familiar cambios (cheque/transferencia)"),
        )


adapter = FamiliarAdapter()
