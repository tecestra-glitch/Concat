from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import myd
from fronteira_fx.adapters._http import sha256_hex
from fronteira_fx.adapters.base import AdapterResult, AdapterStatus

from .conftest import load

URL = myd.URL


def _quote(res: AdapterResult, base: str, city: str):
    return next(q for q in res.quotes if q.base == base and q.city == city)


def _parse(html: str, captured_at: datetime) -> AdapterResult:
    return myd.adapter.parse(html, captured_at=captured_at, url=URL)


# ------------------------------------------------------------------ parse (offline, exact values)
def test_parse_home_html(captured_at: datetime) -> None:
    res = _parse(load("myd.html"), captured_at)
    assert res.status == AdapterStatus.OK, res.message
    cde_usd = _quote(res, "USD", "CDE")
    assert cde_usd.buy == Decimal("5820") and cde_usd.sell == Decimal("5890")
    asu_usd = _quote(res, "USD", "ASU")
    assert asu_usd.buy == Decimal("5780") and asu_usd.sell == Decimal("5930")
    cde_brl = _quote(res, "BRL", "CDE")
    assert cde_brl.buy == Decimal("1080") and cde_brl.sell == Decimal("1115")
    asu_brl = _quote(res, "BRL", "ASU")
    assert asu_brl.buy == Decimal("1070") and asu_brl.sell == Decimal("1170")
    # the board is repeated three times in the page (desktop/mobile copies): one quote per (city, currency)
    assert len(res.quotes) == 4
    assert cde_usd.quote == "PYG" and cde_usd.unit_note.startswith("PYG por 1 USD")
    assert cde_usd.modality == "cash" and cde_usd.kind == "indicative" and cde_usd.channel == "physical"
    assert cde_usd.branch_id == "myd-cde" and asu_usd.branch_id == "myd-asu"
    assert cde_usd.declared_updated_at is None  # the page publishes no timestamp
    assert cde_usd.context == {"section": "CDE"} and asu_usd.context == {"section": "Asuncion"}


def test_zero_rows_are_skipped(captured_at: datetime) -> None:
    html = load("myd.html").replace("<li>5820<i", "<li>0<i").replace("<li>5890<i", "<li>0<i")
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and "CDE" in (res.message or "") and "USD" in (res.message or "")
    assert len(res.quotes) == 3 and not any(q.base == "USD" and q.city == "CDE" for q in res.quotes)


def test_implausible_values_are_rejected(captured_at: datetime) -> None:
    # a BRL flag row carrying USD-sized numbers is a mislabelled flag, not a quote
    html = load("myd.html").replace("<li>1080<i", "<li>5800<i").replace("<li>1115<i", "<li>5900<i")
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and "implausible" in (res.message or "")
    assert len(res.quotes) == 3 and not any(q.base == "BRL" and q.city == "CDE" for q in res.quotes)


def test_missing_city_section_is_degraded(captured_at: datetime) -> None:
    # the CDE board is repeated three times, once as <h2 class="black">CDE</h2>: rename every copy
    html = re.sub(r"(<h2[^>]*>)CDE(</h2>)", r"\1Encarnación\2", load("myd.html"))
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and "CDE" in (res.message or "")
    assert {q.city for q in res.quotes} == {"ASU"} and len(res.quotes) == 2


def test_flag_src_with_cache_buster_still_maps(captured_at: datetime) -> None:
    # WordPress cache plugins append ?ver=... to uploads; the file name is still the flag
    html = load("myd.html").replace("uploads/us-1.png", "uploads/us-1.png?ver=1699")
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.OK, res.message
    assert _quote(res, "USD", "CDE").buy == Decimal("5820") and len(res.quotes) == 4


def test_stub_first_copy_falls_back_to_next_copy(captured_at: datetime) -> None:
    # the first (desktop) copy of the Asuncion board lost its rows; the mobile copies still carry them
    html = load("myd.html")
    head, h2, tail = html.partition("<h2>Asuncion</h2>")
    block, next_h2, rest = tail.partition("<h2>")
    html = head + h2 + re.sub(r"<ul>.*?</ul>", "", block, flags=re.S) + next_h2 + rest
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 4 and _quote(res, "USD", "ASU").buy == Decimal("5780")


def test_sections_vanished_is_degraded(captured_at: datetime) -> None:
    html = load("myd.html").replace('class="cambios-banner-wrap"', 'class="banner"')
    res = _parse(html, captured_at)
    assert res.status == AdapterStatus.DEGRADED and res.quotes == []
    assert "cambios-banner-wrap" in (res.message or "")
    assert res.evidence is not None and res.evidence.sha256 == sha256_hex(html)


def test_empty_and_json_payloads_are_errors(captured_at: datetime) -> None:
    assert _parse("", captured_at).status == AdapterStatus.ERROR
    assert _parse('{"Asuncion": {"USD": [5780, 5930]}}', captured_at).status == AdapterStatus.ERROR


def test_evidence(captured_at: datetime) -> None:
    html = load("myd.html")
    res = _parse(html, captured_at)
    ev = res.evidence
    assert ev is not None and ev.kind == "html" and ev.url == URL and ev.source_id == "myd"
    assert ev.sha256 == sha256_hex(html) and ev.captured_at == captured_at
    assert "5820" in ev.excerpt and "5890" in ev.excerpt and len(ev.excerpt) <= 2000
    assert ev.rules and "cambios-banner-wrap" in ev.rules[0]


# ------------------------------------------------------------------ fetch (respx, never the real site)
@pytest.mark.asyncio
@respx.mock
async def test_fetch_ok() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=load("myd.html")))
    res = await myd.adapter.fetch()
    assert route.called
    assert res.status == AdapterStatus.OK, res.message
    assert _quote(res, "USD", "CDE").buy == Decimal("5820") and _quote(res, "USD", "CDE").sell == Decimal("5890")
    assert res.evidence is not None and res.evidence.url == URL and res.evidence.kind == "html"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_403_is_blocked() -> None:
    respx.get(URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await myd.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == [] and "403" in (res.message or "")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_recaptcha_challenge_is_blocked() -> None:
    challenge = "<html><head><title>Attention Required!</title></head><body>Please complete the captcha</body></html>"
    respx.get(URL).mock(return_value=httpx.Response(200, text=challenge))
    res = await myd.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_page_without_sections_is_degraded() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html><body><h1>M&D Cambios</h1></body></html>"))
    res = await myd.adapter.fetch()
    assert res.status == AdapterStatus.DEGRADED and res.quotes == [] and res.evidence is not None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_timeout_is_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    res = await myd.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and "timeout" in (res.message or "").lower()


def test_info() -> None:
    info = myd.adapter.info
    assert info.id == "myd" and info.kind == "exchange_house" and info.method == "html"
    assert info.url == URL and info.url.startswith("https://www.mydcambios.com.py")
    assert info.cities == ["ASU", "CDE"] and set(info.currencies) == {"USD", "BRL", "PYG"}
    assert info.allowed_domains == ["www.mydcambios.com.py"]
    assert info.poll_interval_s >= 60 and info.limitations
