from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import bonanza
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

URL = bonanza.API_BOARD


def _q(quotes, branch_id, base):
    return next(q for q in quotes if q.branch_id == branch_id and q.base == base)


FRESH = datetime(2026, 10, 31, 16, 0, tzinfo=UTC)  # fixture declared 2026-10-31T13:02:45Z


def test_parse_board() -> None:
    res = bonanza.adapter.parse(load("bonanza.json"), captured_at=FRESH, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 8  # 4 branches x (USD, BRL)
    matriz_usd = _q(res.quotes, "bonanza-matriz", "USD")
    assert (matriz_usd.buy, matriz_usd.sell) == (Decimal("5830"), Decimal("5920"))
    assert matriz_usd.city == "CDE" and matriz_usd.unit_note == "PYG por 1 USD" and matriz_usd.quote == "PYG"
    matriz_brl = _q(res.quotes, "bonanza-matriz", "BRL")
    assert (matriz_brl.buy, matriz_brl.sell) == (Decimal("1080"), Decimal("1140"))
    jebai_brl = _q(res.quotes, "bonanza-jebai", "BRL")
    assert (jebai_brl.buy, jebai_brl.sell) == (Decimal("1080"), Decimal("1160")) and jebai_brl.city == "CDE"
    parana_usd = _q(res.quotes, "bonanza-parana", "USD")
    assert (parana_usd.buy, parana_usd.sell) == (Decimal("5800"), Decimal("5940")) and parana_usd.city is None
    asu_brl = _q(res.quotes, "bonanza-asuncion", "BRL")
    assert (asu_brl.buy, asu_brl.sell) == (Decimal("1050"), Decimal("1150")) and asu_brl.city == "ASU"
    assert matriz_usd.declared_updated_at == datetime(2026, 10, 31, 13, 2, 45, tzinfo=UTC)
    assert all(q.modality == "cash" and q.channel == "physical" and q.kind == "indicative" for q in res.quotes)
    assert res.evidence is not None and res.evidence.kind == "json"
    # arbitrage rows (Dolar x Real) are never emitted as PYG quotes
    assert all(q.buy < 10000 for q in res.quotes)


def test_stale(captured_at: datetime, much_later: datetime) -> None:
    # 2026-11-02T06Z is 41h after the declared update -> stale (36h policy), quotes kept
    res = bonanza.adapter.parse(load("bonanza.json"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 8 and "old" in (res.message or "")
    assert bonanza.adapter.parse(load("bonanza.json"), captured_at=much_later, url=URL).status == AdapterStatus.STALE


def test_bad_payloads(captured_at: datetime) -> None:
    assert bonanza.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert bonanza.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    shell = bonanza.adapter.parse(load("bonanza_shell.html"), captured_at=captured_at, url=bonanza.HOME_URL)
    assert shell.status == AdapterStatus.ERROR and "api/board" in (shell.message or "")
    no_prices = json.loads(load("bonanza.json"))
    for suc in no_prices["sucursales"]:
        for row in suc["cotizaciones"]:
            row["compra"] = 0
            row["venta"] = 0
    res = bonanza.adapter.parse(json.dumps(no_prices), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []  # zeros are not quotes


def test_partial_branch_is_degraded() -> None:
    data = json.loads(load("bonanza.json"))
    data["sucursales"][0]["cotizaciones"] = [
        r for r in data["sucursales"][0]["cotizaciones"] if r["prefix"] != "brasil"
    ]
    res = bonanza.adapter.parse(json.dumps(data), captured_at=FRESH, url=URL)
    assert res.status == AdapterStatus.DEGRADED and "missing BRL" in (res.message or "")
    assert len(res.quotes) == 7


def _fresh_board() -> str:
    data = json.loads(load("bonanza.json"))
    data["actualizado"] = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return json.dumps(data)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_happy_path() -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, text=_fresh_board(), headers={"content-type": "application/json"})
    )
    res = await bonanza.adapter.fetch()
    assert route.called
    assert route.calls.last.request.headers["user-agent"].startswith("Mozilla/5.0")
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 8 and res.evidence is not None and res.evidence.url == URL


@pytest.mark.asyncio
@respx.mock
async def test_fetch_403_is_blocked() -> None:
    respx.get(URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await bonanza.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED
    assert res.quotes == [] and "403" in (res.message or "")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_timeout_is_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    res = await bonanza.adapter.fetch()
    assert res.status == AdapterStatus.ERROR
    assert "timeout" in (res.message or "").lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_500_is_error_not_blocked() -> None:
    respx.get(URL).mock(return_value=httpx.Response(500, text="oops"))
    res = await bonanza.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and "500" in (res.message or "")
