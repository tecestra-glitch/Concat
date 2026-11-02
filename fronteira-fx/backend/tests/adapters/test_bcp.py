from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fronteira_fx.adapters import bcp
from fronteira_fx.adapters._http import TZ_ASUNCION
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load, without_tables

URL = bcp.URL


def test_parse_reference_table(captured_at: datetime) -> None:
    res = bcp.adapter.parse(load("bcp.html"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 2
    usd = next(q for q in res.quotes if q.base == "USD")
    brl = next(q for q in res.quotes if q.base == "BRL")
    # "5.944,76" and "1.100,01" guaraníes per unit (planilla 30/10/2026)
    assert usd.buy == usd.sell == Decimal("5944.76")
    assert brl.buy == brl.sell == Decimal("1100.01")
    assert usd.quote == "PYG" and usd.unit_note.startswith("PYG por 1 USD")
    assert "sem compra/venta" in usd.unit_note
    assert usd.kind == "market_reference" and usd.city is None and usd.channel == "digital"
    assert usd.declared_updated_at == datetime(2026, 10, 30, tzinfo=TZ_ASUNCION)
    assert res.evidence is not None and res.evidence.kind == "html" and "2026-10-30" in res.evidence.excerpt


def test_header_date_fallback(captured_at: datetime) -> None:
    html = load("bcp.html").replace('value="30/10/2026"', 'value=""')
    res = bcp.adapter.parse(html, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.OK
    assert res.quotes[0].declared_updated_at == datetime(2026, 10, 30, tzinfo=TZ_ASUNCION)


def test_stale_after_four_days() -> None:
    html = load("bcp.html")
    assert bcp.adapter.parse(html, captured_at=datetime(2026, 11, 2, 6, tzinfo=UTC), url=URL).status == AdapterStatus.OK
    res = bcp.adapter.parse(html, captured_at=datetime(2026, 11, 6, 6, tzinfo=UTC), url=URL)
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 2


def test_layout_change(captured_at: datetime) -> None:
    assert bcp.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    res = bcp.adapter.parse(without_tables(load("bcp.html")), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and res.message
    no_brl = load("bcp.html").replace(">BRL<", ">XXX<")
    res = bcp.adapter.parse(no_brl, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "") and len(res.quotes) == 1


def test_info() -> None:
    assert bcp.adapter.info.kind == "central_bank" and bcp.adapter.info.id == "bcp"
