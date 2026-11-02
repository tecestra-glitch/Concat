"""M&D Cambios (https://www.mydcambios.com.py/).

Server-rendered home page. The board is one block per city, repeated three times for the
desktop/mobile layouts::

    <div class="cambios-banner-wrap">
      <h2>Asuncion</h2>                                   <!-- or <h2>CDE</h2> -->
      <div class="cambios-banner-text scrollbox">
        <ul><li>.</li><li>Compra</li><li>Venta</li></ul>  <!-- header row -->
        <ul><li><img src=".../uploads/us-1.png"></li>
            <li>5780<i class="fa fa-location-arrow"></i></li><li>5930<i ...></i></li></ul>
        ...

There is no ISO code anywhere: the currency is identified only by the flag image's file name
(``us-1.png`` = USD; ``br.png`` = BRL on the CDE board; ``descarga.png`` = BRL on the Asunción
board, a default download name). Rows of other currencies are ignored and ``0`` means "not
traded". Because the mapping rests on file names, every value is checked against a plausibility
band before it becomes a quote. The page publishes no update timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ._common import as_text, city_from_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, QuoteDraft

URL = "https://www.mydcambios.com.py/"
RULE = (
    "myd html v1 (.cambios-banner-wrap h2 = city; .cambios-banner-text ul: li img flag, li compra, li venta; "
    "flags us-1.png=USD, br.png|descarga.png=BRL; plausibility bands per currency)"
)
SECTION = ".cambios-banner-wrap"
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
CITIES: tuple[str, ...] = ("ASU", "CDE")
FLAG_FILES: dict[str, str] = {"us-1.png": "USD", "br.png": "BRL", "descarga.png": "BRL"}
# PYG per 1 unit. A value outside the band means the flag was mislabelled, not that the price moved.
PLAUSIBLE: dict[str, tuple[Decimal, Decimal]] = {
    "USD": (Decimal(3000), Decimal(15000)),
    "BRL": (Decimal(500), Decimal(3000)),
}


def _flag_iso(cell: LexborNode) -> str | None:
    img = cell.css_first("img")
    if img is None:
        return None
    path = urlsplit((img.attributes.get("src") or "").strip()).path  # drop ?ver=... cache busters
    return FLAG_FILES.get(unquote(path.rsplit("/", 1)[-1]).lower())


class MydAdapter:
    info = AdapterInfo(
        id="myd",
        name="M&D Cambios",
        kind="exchange_house",
        method="html",
        url=URL,
        capabilities=["buy_sell", "usd_pyg", "brl_pyg", "boards_asu_cde"],
        limitations=[
            "moeda identificada só pelo nome do arquivo da bandeira (us-1.png, br.png, descarga.png); "
            "uma faixa de plausibilidade descarta bandeira trocada",
            "a página não publica horário de atualização: a idade vem do hash do conteúdo no collector",
            "cotação de balcão indicativa; o valor efetivo depende do montante e da sucursal",
            "linhas com 0 significam moeda não negociada e são ignoradas",
        ],
        cities=list(CITIES),
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.mydcambios.com.py"],
    )
    stale_after = timedelta(hours=36)  # never triggers today: the page declares no timestamp

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
        sections = tree.css(SECTION)
        if not sections:
            return AdapterResult(
                status=AdapterStatus.DEGRADED, quotes=[], evidence=self._evidence(text, url, captured_at, []),
                message=f"no {SECTION} sections found (layout changed?)",
            )
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        seen: set[tuple[str, str]] = set()
        reported: set[tuple[str, str]] = set()
        cities_seen: set[str] = set()
        for section in sections:
            h2 = section.css_first("h2")
            label = h2.text(strip=True) if h2 else ""
            city = city_from_text(label)
            if city is None or city not in CITIES or city in cities_seen:
                continue  # unknown city, or a repeated desktop/mobile copy of a board already read
            for row in section.css(".cambios-banner-text ul"):
                cells = row.css("li")
                if len(cells) < 3:
                    continue
                iso = _flag_iso(cells[0])
                if iso is None or (city, iso) in seen or (city, iso) in reported:
                    continue
                buy = positive_or_none(try_parse_decimal(cells[1].text(strip=True), "es_PY"))
                sell = positive_or_none(try_parse_decimal(cells[2].text(strip=True), "es_PY"))
                if buy is None and sell is None:
                    issues.append(f"{label}: {iso} has no positive prices")
                    reported.add((city, iso))
                    continue
                lo, hi = PLAUSIBLE[iso]
                if any(v is not None and not (lo <= v <= hi) for v in (buy, sell)):
                    issues.append(
                        f"{label}: {iso} implausible {buy}/{sell} "
                        f"(expected {lo}..{hi} PYG por 1 {iso}; flag mislabelled?)"
                    )
                    reported.add((city, iso))
                    continue
                seen.add((city, iso))
                cities_seen.add(city)  # only a copy that yielded a quote counts; a stub copy lets the next one be read
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id, base=iso, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                        unit_note=f"PYG por 1 {iso}", modality="cash", kind="indicative", channel="physical",
                        city=city, branch_id=f"myd-{city.lower()}", context={"section": label},
                    )
                )
        for city in CITIES:
            if city not in cities_seen:
                issues.append(f"missing {city} section")
                continue
            for iso in sorted(CURRENCIES):
                if (city, iso) not in seen and (city, iso) not in reported:
                    issues.append(f"{city}: missing {iso}")
        evidence = self._evidence(text, url, captured_at, quotes)
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    def _evidence(self, text: str, url: str, captured_at: datetime, quotes: list[QuoteDraft]) -> EvidenceDraft:
        return build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=[RULE],
            excerpt_text=quotes_excerpt(quotes, header="myd boards Asuncion / CDE"),
        )


adapter = MydAdapter()
