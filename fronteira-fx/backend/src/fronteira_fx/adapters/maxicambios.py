"""MaxiCambios (https://www.maxicambios.com.py/).

The home page is an Angular app, but the server ships the rendered board, so plain
HTTP is enough (no Playwright). Four boards share one card markup, ``div.cotizDivSmall``::

    <div class="cotizDivSmall ...">
      <img src=".../flags/USD.png"> <p>Dólar</p>
      <p>Compra</p><p>5700 <img src="equal.svg"></p>
      <p>Venta</p><p>5950 <img src="equal.svg"></p>
    </div>

* ``#cotizacion-carousel``  principal board (Asunción, casa central): one card per currency
* ``#cotizacion-cd``        Ciudad del Este board (not read in this round: ``cities=["ASU"]``)
* ``#cotizacion-cheq-tra``  cheques / transferencias (not read)
* ``#cotizacion-arbi``      "Arbitraje" cross rates in two columns (``#header-title-board``
  ASUNCIÓN / CDE); the card whose flags are BRL + USD is "Real x Dólar" = BRL por 1 USD
  (``4.85`` / ``5.40``: the dot is the decimal mark, never thousands)

Everything is repeated in a mobile copy (``#cotizacion-carousel-xs`` ...); only the desktop
ids are read, so nothing is duplicated. The footer ``* Ultima actualización: 31/10/2026 - 12:10.``
(America/Asuncion) is the declared timestamp.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ._common import as_text, city_from_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import (
    TZ_ASUNCION,
    build_evidence,
    default_headers,
    http_get,
    positive_or_none,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

URL = "https://www.maxicambios.com.py/"
RULE = (
    "maxicambios html v1 (#cotizacion-carousel .cotizDivSmall: img flags/<ISO>.png, p Compra/Venta; "
    "#cotizacion-arbi column ASUNCIÓN card BRL+USD 'Real x Dólar' = BRL por 1 USD; "
    "footer '* Ultima actualización: dd/mm/yyyy - HH:MM')"
)
PRINCIPAL_BOARD = "#cotizacion-carousel"
CROSS_BOARD = "#cotizacion-arbi"
CARD = ".cotizDivSmall"
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
CITY = "ASU"
BRANCH_ID = "maxicambios-asu"

_FLAG_RE = re.compile(r"/flags/([A-Za-z]{3})\.png", re.I)
_UPDATED_RE = re.compile(r"ltima\s+actualizaci\S*?n\s*:\s*([^<]{0,60})", re.I)
_TS_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s*-?\s*(\d{1,2}:\d{2})")


def _flags(card: LexborNode) -> list[str]:
    isos: list[str] = []
    for img in card.css("img"):
        m = _FLAG_RE.search(img.attributes.get("src") or "")
        if m:
            isos.append(m.group(1).upper())
    return isos


def _card_fields(card: LexborNode) -> tuple[str, str | None, str | None]:
    """(label, compra text, venta text) read from the card's <p> sequence."""
    texts = [p.text(strip=True) for p in card.css("p")]
    label = texts[0] if texts and texts[0].lower() not in ("compra", "venta") else ""
    buy = sell = None
    for i, t in enumerate(texts[:-1]):
        key = t.lower()
        if key == "compra" and buy is None:
            buy = texts[i + 1]
        elif key == "venta" and sell is None:
            sell = texts[i + 1]
    return label, buy, sell


def _declared(text: str, issues: list[str]) -> datetime | None:
    m = _UPDATED_RE.search(text)
    if not m:
        issues.append("'Ultima actualización' timestamp not found")
        return None
    raw = m.group(1).strip()
    ts = _TS_RE.search(raw)
    if ts:
        try:
            return datetime.strptime(f"{ts.group(1)} {ts.group(2)}", "%d/%m/%Y %H:%M").replace(tzinfo=TZ_ASUNCION)
        except ValueError:
            pass
    issues.append(f"unparsable 'Ultima actualización' timestamp {raw!r}")
    return None


class MaxiCambiosAdapter:
    info = AdapterInfo(
        id="maxicambios",
        name="MaxiCambios",
        kind="exchange_house",
        method="html",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "brl_pyg", "cross_usd_brl", "declared_update_ts", "board_asu"],
        limitations=[
            "só o quadro principal (Assunção, casa central); os quadros de CDE, cheques e transferências não são lidos",
            "HTML renderizado por Angular: se o servidor passar a entregar só o shell, os cards somem (DEGRADED)",
            "cotação de balcão indicativa; o valor efetivo depende do montante e da sucursal",
            "cruzado 'Real x Dólar' (BRL por 1 USD) é opcional: ausente, só gera nota",
            "a página embute reCAPTCHA v3 (badge); um desafio real (403/página de captcha) devolve BLOCKED",
        ],
        cities=[CITY],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.maxicambios.com.py"],
    )
    # The board is not refreshed over the weekend (capture: Sat 31/10 12:10 read on Mon 02/11 early morning).
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
            return error_result("JSON payload; expected the HTML board")
        text = as_text(raw)
        tree = LexborHTMLParser(text)
        if not tree.css(CARD):
            return AdapterResult(
                status=AdapterStatus.DEGRADED, quotes=[], evidence=self._evidence(text, url, captured_at, []),
                message=f"no {CARD} cards found (layout changed, or shell served without the rendered board?)",
            )
        issues: list[str] = []
        notes: list[str] = []
        declared = _declared(text, issues)
        quotes = self._principal(tree, declared, issues)
        cross = self._cross(tree, declared, notes)
        if cross is not None:
            quotes.append(cross)
        evidence = self._evidence(text, url, captured_at, quotes)
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _principal(self, tree: LexborHTMLParser, declared: datetime | None, issues: list[str]) -> list[QuoteDraft]:
        board = tree.css_first(PRINCIPAL_BOARD)
        if board is None:
            issues.append(f"principal board {PRINCIPAL_BOARD} not found")
            return []
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for card in board.css(CARD):
            flags = _flags(card)
            iso = flags[0] if len(flags) == 1 else None
            if iso is None or iso not in CURRENCIES or iso in seen:
                continue
            label, buy_txt, sell_txt = _card_fields(card)
            buy = positive_or_none(try_parse_decimal(buy_txt, "es_PY")) if buy_txt else None
            sell = positive_or_none(try_parse_decimal(sell_txt, "es_PY")) if sell_txt else None
            seen.add(iso)
            if buy is None and sell is None:
                issues.append(f"{iso} ({label or '?'}): no positive prices")
                continue
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base=iso, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                    unit_note=f"PYG por 1 {iso}", modality="cash", kind="indicative", channel="physical",
                    city=CITY, branch_id=BRANCH_ID, context={"board": "principal"}, declared_updated_at=declared,
                )
            )
        for missing in sorted(CURRENCIES - seen):
            issues.append(f"missing {missing} card on principal board")
        return quotes

    def _cross(self, tree: LexborHTMLParser, declared: datetime | None, notes: list[str]) -> QuoteDraft | None:
        board = tree.css_first(CROSS_BOARD)
        if board is None:
            notes.append(f"cross 'Real x Dólar' not present ({CROSS_BOARD} missing; optional)")
            return None
        for column in board.css("div.col-sm-6"):
            # the column is the .col-sm-6 that holds a #header-title-board (at any depth); the ASUNCIÓN/CDE title
            # cells are .col-sm-6 too but contain no header, so they are skipped
            header = column.css_first("#header-title-board")
            if header is None or city_from_text(header.text(strip=True)) != CITY:
                continue
            for card in column.css(CARD):
                if set(_flags(card)) != {"BRL", "USD"}:
                    continue
                label, buy_txt, sell_txt = _card_fields(card)
                # en_US: "4.85" / "5.40" use the dot as decimal mark (a BRL/USD cross is never in the hundreds)
                buy = positive_or_none(try_parse_decimal(buy_txt, "en_US")) if buy_txt else None
                sell = positive_or_none(try_parse_decimal(sell_txt, "en_US")) if sell_txt else None
                if buy is None and sell is None:
                    notes.append(f"cross {label or 'Real x Dólar'!r}: no positive prices")
                    return None
                return QuoteDraft(
                    source_id=self.info.id, base="USD", quote="BRL", buy=buy, sell=sell,
                    unit_note="BRL por 1 USD (cruzado 'Real x Dólar' do quadro Arbitraje)",
                    modality="cash", kind="indicative", channel="physical", city=CITY, branch_id=BRANCH_ID,
                    context={"board": "arbitraje", "pair": label or "Real x Dólar"}, declared_updated_at=declared,
                )
        notes.append(f"cross 'Real x Dólar' not found in {CROSS_BOARD} (optional)")
        return None

    def _evidence(self, text: str, url: str, captured_at: datetime, quotes: list[QuoteDraft]) -> EvidenceDraft:
        return build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=quotes_excerpt(quotes, header="maxicambios principal board (ASU) + arbitraje cross"),
        )


adapter = MaxiCambiosAdapter()
