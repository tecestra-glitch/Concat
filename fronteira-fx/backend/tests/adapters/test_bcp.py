from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import bcp
from fronteira_fx.adapters._http import TZ_ASUNCION
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load, without_tables

URL = bcp.URL
FEED = bcp.FRANKFURTER_URL


def _usd_brl(res):
    return next(q for q in res.quotes if q.base == "USD"), next(q for q in res.quotes if q.base == "BRL")


def test_parse_frankfurter_json(captured_at: datetime) -> None:
    res = bcp.adapter.parse(load("bcp_frankfurter.json"), captured_at=captured_at, url=FEED)
    assert res.status == AdapterStatus.OK, res.message
    usd, brl = _usd_brl(res)
    assert usd.buy == usd.sell == Decimal("5944.76")  # USD/PYG ~ 5,945 (never the 1.0000 "ME/USD" column)
    assert brl.buy == brl.sell == Decimal("1100.01")
    assert usd.quote == "PYG" and usd.unit_note.startswith("PYG por 1 USD") and "sem compra/venta" in usd.unit_note
    assert usd.kind == "market_reference" and usd.city is None and usd.channel == "digital"
    assert usd.declared_updated_at == datetime(2026, 10, 30, tzinfo=TZ_ASUNCION)
    assert res.evidence is not None and res.evidence.kind == "json" and "2026-10-30" in res.evidence.excerpt


def test_json_derives_brl_from_usd_cross(captured_at: datetime) -> None:
    entries = [e for e in json.loads(load("bcp_frankfurter.json")) if e["base"] == "USD"]  # USD->BRL 5.4043, USD->PYG
    res = bcp.adapter.parse(json.dumps(entries), captured_at=captured_at, url=FEED)
    assert res.status == AdapterStatus.OK, res.message
    _, brl = _usd_brl(res)
    assert brl.buy == Decimal("1100.01") and "derivado" in brl.unit_note


def test_json_bad_shapes(captured_at: datetime) -> None:
    assert bcp.adapter.parse("[]", captured_at=captured_at, url=FEED).status == AdapterStatus.ERROR
    assert bcp.adapter.parse('{"message": "nope"}', captured_at=captured_at, url=FEED).status == AdapterStatus.ERROR
    only_usd = json.dumps([{"date": "2026-10-30", "base": "USD", "quote": "PYG", "rate": 5944.76}])
    res = bcp.adapter.parse(only_usd, captured_at=captured_at, url=FEED)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "") and len(res.quotes) == 1
    zero = json.dumps([{"date": "2026-10-30", "base": "USD", "quote": "PYG", "rate": 0}])
    assert bcp.adapter.parse(zero, captured_at=captured_at, url=FEED).status == AdapterStatus.ERROR


def test_parse_reference_table_html(captured_at: datetime) -> None:
    res = bcp.adapter.parse(load("bcp.html"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 2
    usd, brl = _usd_brl(res)
    # "5.944,76" and "1.100,01" guaraníes per unit (planilla 30/10/2026)
    assert usd.buy == usd.sell == Decimal("5944.76")
    assert brl.buy == brl.sell == Decimal("1100.01")
    assert usd.declared_updated_at == datetime(2026, 10, 30, tzinfo=TZ_ASUNCION)
    assert res.evidence is not None and res.evidence.kind == "html" and "2026-10-30" in res.evidence.excerpt


def test_header_date_fallback(captured_at: datetime) -> None:
    html = load("bcp.html").replace('value="30/10/2026"', 'value=""')
    res = bcp.adapter.parse(html, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK
    assert res.quotes[0].declared_updated_at == datetime(2026, 10, 30, tzinfo=TZ_ASUNCION)


def test_stale_after_four_days() -> None:
    for payload, url in ((load("bcp.html"), URL), (load("bcp_frankfurter.json"), FEED)):
        assert bcp.adapter.parse(payload, captured_at=datetime(2026, 11, 2, 6, tzinfo=UTC), url=url).status == AdapterStatus.OK
        res = bcp.adapter.parse(payload, captured_at=datetime(2026, 11, 6, 6, tzinfo=UTC), url=url)
        assert res.status == AdapterStatus.STALE and len(res.quotes) == 2


def test_layout_change(captured_at: datetime) -> None:
    assert bcp.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    res = bcp.adapter.parse(without_tables(load("bcp.html")), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and res.message
    no_brl = load("bcp.html").replace(">BRL<", ">XXX<")
    res = bcp.adapter.parse(no_brl, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "") and len(res.quotes) == 1


def _fresh_feed(base: str, quote: str) -> list[dict]:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    rate = 5944.76 if base == "USD" else 1100.01
    return [{"date": today, "base": base, "quote": quote, "rate": rate}]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prefers_frankfurter() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.params["quotes"] == "PYG"
        return httpx.Response(200, json=_fresh_feed(request.url.params["base"], "PYG"))

    feed = respx.get(url__startswith=FEED).mock(side_effect=responder)
    page = respx.get(URL).mock(return_value=httpx.Response(200, text=load("bcp.html")))
    res = await bcp.adapter.fetch()
    assert res.status == AdapterStatus.OK, res.message
    assert feed.call_count == 2 and not page.called
    usd, brl = _usd_brl(res)
    assert usd.buy == Decimal("5944.76") and brl.buy == Decimal("1100.01")
    assert res.evidence is not None and res.evidence.url == FEED


@pytest.mark.asyncio
@respx.mock
async def test_fetch_falls_back_to_html() -> None:
    respx.get(url__startswith=FEED).mock(return_value=httpx.Response(503, text="down"))
    html = load("bcp.html").replace('value="30/10/2026"', f'value="{datetime.now(tz=UTC).strftime("%d/%m/%Y")}"')
    page = respx.get(URL).mock(return_value=httpx.Response(200, text=html))
    res = await bcp.adapter.fetch()
    assert page.called
    assert res.status == AdapterStatus.OK, res.message
    assert "html fallback" in (res.message or "") and "503" in (res.message or "")
    assert res.evidence is not None and res.evidence.kind == "html"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_both_sources_down() -> None:
    respx.get(url__startswith=FEED).mock(side_effect=httpx.ConnectTimeout("slow"))
    respx.get(URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await bcp.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == []
    assert "timeout" in (res.message or "").lower() and "403" in (res.message or "")


def test_info() -> None:
    assert bcp.adapter.info.kind == "central_bank" and bcp.adapter.info.id == "bcp"
    assert bcp.adapter.info.method == "official_api"
    assert set(bcp.adapter.info.allowed_domains) == {"api.frankfurter.dev", "www.bcp.gov.py"}
