from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import dolarpy
from fronteira_fx.adapters._http import TZ_ASUNCION, sha256_hex
from fronteira_fx.adapters.base import AdapterResult, AdapterStatus

from .conftest import load

URL = dolarpy.URL
# The capture says "updated": "2026-10-30 20:50:24" (Asunción, -03:00 = 23:50:24Z); ~6h later is fresh.
FRESH = datetime(2026, 10, 31, 6, 0, tzinfo=UTC)
HOUSES = {
    "bcp", "bonanza", "cambiosalberdi", "cambioschaco", "continental", "eurocambios", "familiar",
    "gnbfusion", "lamoneda", "maxicambios", "mundialcambios", "mydcambios", "set",  # ueno: banco fechado, pulado
}


def _house(res: AdapterResult, name: str):
    return next(q for q in res.quotes if (q.context or {}).get("house") == name)


def _parse(payload: str, captured_at: datetime = FRESH) -> AdapterResult:
    return dolarpy.adapter.parse(payload, captured_at=captured_at, url=URL)


# ------------------------------------------------------------------ parse (offline, exact values)
def test_parse_one_quote_per_house() -> None:
    res = _parse(load("dolarpy.json"))
    assert res.status == AdapterStatus.OK, res.message
    maxi = _house(res, "maxicambios")
    assert maxi.buy == Decimal("5700.0") and maxi.sell == Decimal("5950.0")
    assert maxi.base == "USD" and maxi.quote == "PYG" and maxi.city is None
    assert maxi.branch_id == "dolarpy-maxicambios"
    assert maxi.context == {"aggregator": "dolarpy", "house": "maxicambios"}
    assert maxi.declared_updated_at == datetime(2026, 10, 30, 20, 50, 24, tzinfo=TZ_ASUNCION)
    assert maxi.unit_note.startswith("PYG por 1 USD") and "não executável" in maxi.unit_note
    bcp = _house(res, "bcp")
    assert bcp.buy == Decimal("5908.35") and bcp.sell == Decimal("5922.67")  # never the referencial_diario column
    assert len(res.quotes) == 13 and {q.context["house"] for q in res.quotes} == HOUSES


def test_every_quote_is_reference_only() -> None:
    res = _parse(load("dolarpy.json"))
    assert res.quotes
    for q in res.quotes:
        assert q.modality == "reference" and q.channel == "aggregator" and q.kind == "market_reference"
        assert q.source_id == "dolarpy"


def test_stale_after_24h(captured_at: datetime) -> None:
    payload = load("dolarpy.json")
    # 23h49m after "updated" -> still OK; 24h09m -> STALE (quotes kept so the collector can store them as stale)
    assert _parse(payload, datetime(2026, 10, 31, 23, 40, tzinfo=UTC)).status == AdapterStatus.OK
    res = _parse(payload, datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 13 and "old" in (res.message or "")
    assert _parse(payload, captured_at).status == AdapterStatus.STALE  # the shared 2026-11-02 instant: 54h


def test_bad_payloads_are_errors() -> None:
    assert _parse("").status == AdapterStatus.ERROR
    res = _parse("{not json")
    assert res.status == AdapterStatus.ERROR and "invalid JSON" in (res.message or "")
    assert _parse("[]").status == AdapterStatus.ERROR
    assert _parse('{"dolarpy": {}, "updated": "2026-10-30 20:50:24"}').status == AdapterStatus.ERROR
    assert _parse('{"updated": "2026-10-30 20:50:24"}').status == AdapterStatus.ERROR
    assert _parse("<html><body>maintenance</body></html>").status == AdapterStatus.ERROR
    zeros = {"dolarpy": {"x": {"compra": 0, "venta": 0}}, "updated": "2026-10-30 20:50:24"}
    res = _parse(json.dumps(zeros))
    assert res.status == AdapterStatus.ERROR and res.quotes == []  # zeros never become quotes


def test_broken_house_is_degraded_not_fatal() -> None:
    payload = {
        "dolarpy": {
            "maxicambios": {"compra": 5700, "venta": 5950},
            "soloventa": {"venta": 5990},
            "broken": {"compra": "n/a"},
            "weird": [1, 2],
        },
        "updated": "2026-10-30 20:50:24",
    }
    res = _parse(json.dumps(payload))
    assert res.status == AdapterStatus.DEGRADED, res.message
    assert "broken" in (res.message or "") and "weird" in (res.message or "")
    assert {q.context["house"] for q in res.quotes} == {"maxicambios", "soloventa"}
    solo = _house(res, "soloventa")
    assert solo.buy is None and solo.sell == Decimal("5990")


def test_missing_updated_is_degraded() -> None:
    payload = {"dolarpy": {"maxicambios": {"compra": 5700, "venta": 5950}}}
    res = _parse(json.dumps(payload))
    assert res.status == AdapterStatus.DEGRADED and "updated" in (res.message or "")
    assert len(res.quotes) == 1 and res.quotes[0].declared_updated_at is None


def test_evidence() -> None:
    payload = load("dolarpy.json")
    res = _parse(payload)
    ev = res.evidence
    assert ev is not None and ev.kind == "json" and ev.url == URL and ev.source_id == "dolarpy"
    assert ev.sha256 == sha256_hex(payload) and ev.captured_at == FRESH
    assert "maxicambios" in ev.excerpt and "5700" in ev.excerpt and "2026-10-30" in ev.excerpt
    assert len(ev.excerpt) <= 2000 and ev.rules and "dolarpy" in ev.rules[0]


# ------------------------------------------------------------------ fetch (respx, never the real API)
def _fresh_payload() -> str:
    data = json.loads(load("dolarpy.json"))
    data["updated"] = datetime.now(tz=TZ_ASUNCION).strftime("%Y-%m-%d %H:%M:%S")
    return json.dumps(data)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_ok() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=_fresh_payload()))
    res = await dolarpy.adapter.fetch()
    assert route.called
    assert res.status == AdapterStatus.OK, res.message
    assert _house(res, "maxicambios").buy == Decimal("5700.0") and len(res.quotes) == 13
    assert res.evidence is not None and res.evidence.url == URL and res.evidence.kind == "json"
    assert "json" in route.calls[0].request.headers["accept"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_injectable_clock_for_staleness() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=load("dolarpy.json")))
    late = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
    res = await dolarpy.DolarPyAdapter(clock=lambda: late).fetch()
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 13
    assert res.evidence is not None and res.evidence.captured_at == late
    fresh = await dolarpy.DolarPyAdapter(clock=lambda: FRESH).fetch()
    assert fresh.status == AdapterStatus.OK and fresh.evidence is not None and fresh.evidence.captured_at == FRESH


@pytest.mark.asyncio
@respx.mock
async def test_fetch_old_updated_is_stale_with_real_clock() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=load("dolarpy.json")))  # updated 2026-10-30
    res = await dolarpy.adapter.fetch()
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 13


@pytest.mark.asyncio
@respx.mock
async def test_fetch_403_is_blocked() -> None:
    respx.get(URL).mock(return_value=httpx.Response(403, text="forbidden"))
    res = await dolarpy.adapter.fetch()
    assert res.status == AdapterStatus.BLOCKED and res.quotes == [] and "403" in (res.message or "")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_timeout_is_error() -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    res = await dolarpy.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and "timeout" in (res.message or "").lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_invalid_json_is_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html><body>maintenance</body></html>"))
    res = await dolarpy.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and res.quotes == []
    respx.get(URL).mock(return_value=httpx.Response(500, text="oops"))
    res = await dolarpy.adapter.fetch()
    assert res.status == AdapterStatus.ERROR and "500" in (res.message or "")


def test_info() -> None:
    info = dolarpy.adapter.info
    assert info.id == "dolarpy" and info.method == "official_api"
    assert info.url == URL == "https://dolar.melizeche.com/api/1.0/"
    assert "aggregator" in info.capabilities and "reference_only" in info.capabilities
    assert info.allowed_domains == ["dolar.melizeche.com"] and info.cities == []
    assert set(info.currencies) == {"USD", "PYG"}
    assert any("executável" in lim for lim in info.limitations)
    assert info.poll_interval_s >= 60


def test_discontinued_houses_are_skipped():
    import json
    from datetime import UTC, datetime

    from fronteira_fx.adapters import dolarpy

    raw = json.dumps({"dolarpy": {"ueno": {"compra": 5800, "venta": 6070}, "cambioschaco": {"compra": 5990, "venta": 6140}},
                      "updated": "2026-11-04 03:00:00"})
    result = dolarpy.adapter.parse(raw, captured_at=datetime(2026, 11, 4, 7, 0, tzinfo=UTC), url=dolarpy.adapter.info.url)
    houses = {(q.context or {}).get("house") for q in result.quotes}
    assert "ueno" not in houses and "cambioschaco" in houses
