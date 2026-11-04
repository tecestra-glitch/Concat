"""Banco Basa (https://www.bancobasa.com.py/), home page "Cotización de monedas" block.

The block is server-rendered. Each quote is an anchor with an image whose file name identifies the currency::

    <img src="/storage/app/media/images/cotizacion/dolar.png" alt="Compra 5.880 | Venta 6.250">
    <p>Compra 5.880 | Venta 6.250</p>

* ``dolar.png``  -> USD / PYG
* ``reales.png`` -> BRL / PYG
* ``euros.png``, ``pesosargentinos.png`` -> not supported by the terminal's currency set (ignored)

Values use es_PY formatting (``5.880`` = 5880). The page publishes no timestamp, so there is no
``declared_updated_at`` and staleness is handled by the collector's content hash.
Channel: bank quote for its own digital/account customers, city None.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

URL = "https://www.bancobasa.com.py/"
RULE = (
    "basa html v1 (img[src*=/cotizacion/] file dolar.png=USD reales.png=BRL; "
    "alt/p 'Compra X | Venta Y' es_PY; PYG por 1 unidade)"
)
_IMAGE_CURRENCY = {"dolar.png": "USD", "reales.png": "BRL"}
_PRICE_RE = re.compile(r"Compra\s*([\d.,]+)\s*\|\s*Venta\s*([\d.,]+)", re.I)


class BasaAdapter:
    info = AdapterInfo(
        id="basa",
        name="Banco Basa",
        kind="bank",
        method="html",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "brl_pyg", "channel_digital"],
        limitations=[
            "cotação publicada na home sem modalidade nem horário declarado; tratada como indicativa",
            "só USD e BRL (EUR e pesos argentinos fora do conjunto de moedas do terminal)",
            "sem cruzamento USD/BRL publicado",
            "sem cidade: o banco não declara sucursal para esta cotação",
        ],
        cities=[],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=900,
        allowed_domains=["www.bancobasa.com.py"],
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
            return error_result("JSON payload; expected the HTML home page")
        text = as_text(raw)
        tree = LexborHTMLParser(text)
        quotes: list[QuoteDraft] = []
        issues: list[str] = []
        seen: set[str] = set()
        for img in tree.css("img[src*='/cotizacion/']"):
            filename = (img.attributes.get("src") or "").rsplit("/", 1)[-1].lower()
            base = _IMAGE_CURRENCY.get(filename)
            if base is None or base in seen:
                continue
            match = _PRICE_RE.search(img.attributes.get("alt") or "")
            if match is None:
                issues.append(f"{base}: price text not found in alt")
                continue
            buy = positive_or_none(try_parse_decimal(match.group(1), "es_PY"))
            sell = positive_or_none(try_parse_decimal(match.group(2), "es_PY"))
            seen.add(base)
            if buy is None or sell is None:
                issues.append(f"{base}: missing positive buy/sell")
                continue
            if buy > sell:
                issues.append(f"{base}: compra {buy} > venta {sell}; labels may be inverted")
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base=base, quote="PYG",  # type: ignore[arg-type]
                    buy=buy, sell=sell, unit_note=f"PYG por 1 {base}", modality="account",
                    kind="indicative", channel="digital", city=None, branch_id=None,
                    context={"source_block": "cotizacion-home"},
                )
            )
        for missing in sorted({"USD", "BRL"} - seen):
            issues.append(f"missing {missing} quote on home block")
        evidence = self._evidence(text, url, captured_at, quotes)
        if not quotes:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence,
                                 message="; ".join(issues) or "no quotes parsed (layout changed?)")
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _evidence(self, text: str, url: str, captured_at: datetime, quotes: list[QuoteDraft]) -> EvidenceDraft:
        return build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=quotes_excerpt(quotes, header="basa home 'Cotización de monedas'"),
        )


adapter = BasaAdapter()
