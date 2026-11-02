from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import maxicambios
from fronteira_fx.adapters._http import TZ_ASUNCION, sha256_hex
from fronteira_fx.adapters.base import AdapterResult, AdapterStatus

from .conftest import load

URL = maxicambios.URL
DECLARED = "31/10/2026 - 12:10"  # "* Ultima actualización: ..." footer of the capture


def _quote(res: AdapterResult, base: str, quote: str = "PYG", board: str = "principal"):
    return next(
        q for q in res.quotes if q.base == base and q.quote == quote and (q.context or {}).get("board") == board
    )


def _parse(html: str, captured_at: datetime) -> AdapterResult:
    return maxicambios.adapter.parse(html, captured_at=captured_at, url=URL)


# ------------------------------------------------------------------ parse (offline, exact values)
def test_parse_principal_board(captured_at: datetime) -> None:
    res = _parse(load("maxicambios.html"), captured_at)
    assert res.status == AdapterStatus.OK, res.message
    usd = _quote(res, "USD")
    assert usd.buy == Decimal("5700") and usd.sell == Decimal("5950")
    assert usd.unit_note.startswith("PYG por 1 USD")
    assert usd.city == "ASU" and usd.modality == "cash" and usd.kind == "indicative" and usd.channel == "physical"
    assert usd.context == {"board": "principal"} and usd.branch_id == "maxicambios-asu"
    assert usd.declared_updated_at == datetime(2026, 10, 31, 12, 10, tzinfo=TZ_ASUNCION)
    brl = _quote(res, "BRL")
    assert brl.buy == Decimal("1100") and brl.sell == Decimal("1180")
    assert brl.unit_note.startswith("PYG por 1 BRL") and brl.city == "ASU"
    # only the desktop principal board + the ASU cross count: no duplicates from the mobile (-xs) copy,
    # the CDE board or the cheques/transfer board
    assert [(q.base, q.quote) for q in res.quotes] == [("USD", "PYG"), ("BRL", "PYG"), ("USD", "BRL")]


def test_parse_cross_real_dolar(captured_at: datetime) -> None:
    res = _parse(load("maxicambios.html"), captured_at)
    cross = _quote(res, "USD", quote="BRL", board="arbitraje")
    assert cross.buy == Decimal("4.85") and cross.sell == Decimal("5.40")  # "." is the decimal mark, never 485
    assert cross.unit_note.startswith("BRL por 1 USD") and cross.city == "ASU"
    assert cross.modality == "cash" and cross.kind == "indicative" and cross.channel == "physical"
    assert cross.context == {"board": "arbitraje", "pair": "Real x Dólar"}


def test_cross_survives_wrapper_around_column_header(captured_at: datetime) -> None:
    # a template change nests the ASUNCIÓN header one level deeper inside its column: still the same column
    html = load("maxicambios.html")
    start = html.index('id="cotizacion-arbi"')
    at = html.index('<div id="header-title-board"', start)
    html = html[:at] + '<div class="hdr-wrap">' + html[at:]
    res = _parse(html, captured_at)
    cross = _quote(res, "USD", quote="BRL", board="arbitraje")
    assert cross.buy == Decimal("4.85") and cross.sell == Decimal("5.40") and cross.city == "ASU"


def test_cross_is_optional(captured_at: datetime) -> None:
    html = load("maxicambios.html").replace('id="cotizacion-arbi"', 'id="cotizacion-outro"')
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 2 and all(q.quote == "PYG" for q in res.quotes)
    assert "Real x D" in (res.message or "")  # noted, not an issue


def test_missing_usd_card_is_degraded(captured_at: datetime) -> None:
    html = load("maxicambios.html").replace("flags/USD.png", "flags/XXX.png")
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and "missing USD" in (res.message or "")
    assert [q.base for q in res.quotes] == ["BRL"]


def test_cards_vanished_is_degraded(captured_at: datetime) -> None:
    html = load("maxicambios.html").replace('class="cotizDivSmall', 'class="cotizCard')
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and res.quotes == []
    assert "cotizDivSmall" in (res.message or "")
    assert res.evidence is not None and res.evidence.sha256 == sha256_hex(html)


def test_empty_and_json_payloads_are_errors(captured_at: datetime) -> None:
    assert _parse("", captured_at).status == AdapterStatus.ERROR
    assert _parse("   \n", captured_at).status == AdapterStatus.ERROR
    assert _parse('{"cotizaciones": []}', captured_at).status == AdapterStatus.ERROR


def test_unparsable_timestamp_is_noted(captured_at: datetime) -> None:
    html = load("maxicambios.html").replace(DECLARED, "ayer")
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and "actualizaci" in (res.message or "").lower()
    assert _quote(res, "USD").declared_updated_at is None and len(res.quotes) == 3


def test_stale_when_declared_update_is_old(captured_at: datetime, much_later: datetime) -> None:
    assert _parse(load("maxicambios.html"), captured_at).status == AdapterStatus.OK
    res = _parse(load("maxicambios.html"), much_later)
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 3
    assert "old" in (res.message or "")


def test_evidence(captured_at: datetime) -> None:
    html = load("maxicambios.html")
    res = _parse(html, captured_at)
    ev = res.evidence
    assert ev is not None and ev.kind == "html" and ev.url == URL and ev.source_id == "maxicambios"
    assert ev.sha256 == sha256_hex(html) and ev.captured_at == captured_at
    assert "5700" in ev.excerpt and "5950" in ev.excerpt and "4.85" in ev.excerpt and len(ev.excerpt) <= 2000
    assert ev.rules and "cotizDivSmall" in ev.rules[0]


# ------------------------------------------------------------------ fetch (respx, never the real site)
def _fresh_page() -> str:
    """The capture declares 31/10/2026; move it to "now" so the fetch tests stay OK regardless of today."""
    return load("maxicambios.html").replace(DECLARED, datetime.now(tz=TZ_ASUNCION).strftime("%d/%m/%Y - %H:%M"))


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ok() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=_fresh_page()))
    res = await maxicambios.adapter.fetch()
    assert route.called
    assert res.status == AdapterStatus.OK, res.message
    assert _quote(res, "USD").buy == Decimal("5700") and _quote(res, "USD").sell == Decimal("5950")
    assert res.evidence is not None and res.evidence.url == URL and res.evidence.kind == "html"
    assert "text/html" in route.calls[0].request.headers["accept"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tolerates_recaptcha_badge_css() -> None:
    # The live page ships `.grecaptcha-badge{...}` CSS near the top; the word alone is not a challenge page.
    html = _fresh_page().replace("<head>", "<head><style>.grecaptcha-badge{visibility:hidden}</style>", 1)
    respx.get(URL).mock(return_value=httpx.Response(200, text=html))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.OK, res.message
    assert _quote(res, "USD").buy == Decimal("5700")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_403_is_blocked() -> None:
    respx.get(URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == [] and "403" in (res.message or "")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_recaptcha_challenge_is_blocked() -> None:
    challenge = (
        "<html><head><title>Just a moment...</title></head>"
        "<body><form><div class='g-recaptcha' data-sitekey='x'>Please complete the captcha</div></form></body></html>"
    )
    respx.get(URL).mock(return_value=httpx.Response(200, text=challenge))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_page_without_cards_is_degraded() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html><body><h1>Maxicambios</h1></body></html>"))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.DEGRADED and res.quotes == [] and res.evidence is not None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_timeout_is_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and "timeout" in (res.message or "").lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_server_error_is_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500, text="oops"))
    res = await maxicambios.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and "500" in (res.message or "")


def test_info() -> None:
    info = maxicambios.adapter.info
    assert info.id == "maxicambios" and info.kind == "exchange_house" and info.method == "html"
    assert info.url == URL and info.url.startswith("https://www.maxicambios.com.py")
    assert info.cities == ["ASU"] and set(info.currencies) == {"USD", "BRL", "PYG"}
    assert info.allowed_domains == ["www.maxicambios.com.py"]
    assert info.poll_interval_s >= 60 and info.limitations
