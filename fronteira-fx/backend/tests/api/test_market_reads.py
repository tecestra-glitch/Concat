"""Rotas de leitura de `api/market_reads.py` (U08): só GET, cache com TTL configurável, referência nunca executável,
indicadores só sobre velas fechadas e nenhuma rota de escrita sob /v1/market."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from fronteira_fx.api.cache import TtlCache
from fronteira_fx.indicators import core
from fronteira_fx.main import create_app
from fronteira_fx.models import FxReferenceQuote, MarketCandle, MarketQuote
from tests.conftest import make_settings

NEW_OPERATIONS = {
    "get_crypto_quotes",
    "get_triangles",
    "list_fx_references",
    "get_macro_series",
    "get_market_indicators",
}


def _now() -> datetime:
    return datetime.now(tz=UTC).replace(microsecond=0)


def test_new_routes_are_get_only_and_live_under_market():
    app = create_app(make_settings(), mount_mcp_server=False)
    found: dict[str, tuple[str, str]] = {}
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            if op.get("operationId") in NEW_OPERATIONS:
                found[op["operationId"]] = (path, method)
    assert set(found) == NEW_OPERATIONS, found
    assert all(path.startswith("/v1/market/") for path, _ in found.values()), found
    assert all(method == "get" for _, method in found.values()), found


def test_market_prefix_has_no_write_routes():
    app = create_app(make_settings(), mount_mcp_server=False)
    writes = [
        (r.path, sorted(r.methods))
        for r in app.routes
        if getattr(r, "path", "").startswith("/v1/market") and set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert writes == []


def test_crypto_quotes_are_reference_and_cached_with_ttl(client, db, app):
    now = _now()
    db.add(
        MarketQuote(
            instrument="BTC/USDT",
            label="Bitcoin em USDT",
            kind="crypto",
            source="binance",
            price=Decimal("64000.5"),
            change_pct=Decimal("1.25"),
            observed_at=now,
            captured_at=now,
            data_mode="real",
        )
    )
    db.commit()
    first = client.get("/v1/market/crypto")
    assert first.status_code == 200
    body = first.json()
    assert body[0]["instrument"] == "BTC/USDT"
    assert body[0]["executable"] is False and body[0]["price"] == "64000.5"
    assert first.headers["cache-control"] == "private, max-age=60"

    row = db.get(MarketQuote, "BTC/USDT")
    row.price = Decimal("65000")
    db.commit()
    assert client.get("/v1/market/crypto").json()[0]["price"] == "64000.5"  # servido do cache
    app.state.read_cache.clear()
    assert client.get("/v1/market/crypto").json()[0]["price"] == "65000"


def test_ttl_zero_disables_cache():
    app = create_app(make_settings(read_cache_ttl_s=0), mount_mcp_server=False)
    with TestClient(app) as c:
        resp = c.get("/v1/market/triangles")
        assert resp.status_code == 200 and resp.json() == []
        assert resp.headers["cache-control"] == "private, max-age=0"
        assert len(app.state.read_cache) == 0


def test_ttl_cache_expires_with_injected_clock():
    now = [0.0]
    cache = TtlCache(clock=lambda: now[0])
    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    assert cache.get_or_set("k", 10, compute) == 1
    now[0] = 9.9
    assert cache.get_or_set("k", 10, compute) == 1
    now[0] = 10.0
    assert cache.get_or_set("k", 10, compute) == 2


def test_ttl_cache_does_not_store_errors_or_when_ttl_is_zero():
    cache = TtlCache(clock=lambda: 0.0)

    def boom():
        raise RuntimeError("falha")

    with pytest.raises(RuntimeError):
        cache.get_or_set("e", 30, boom)
    assert len(cache) == 0
    assert cache.get_or_set("e", 30, lambda: "ok") == "ok"
    assert cache.get_or_set("z", 0, lambda: "sem cache") == "sem cache"
    assert len(cache) == 1


def test_references_are_never_executable(client, db):
    now = _now()
    db.add(
        FxReferenceQuote(
            instrument="USD/BRL",
            source="frankfurter",
            price=Decimal("5.4321"),
            observed_at=now - timedelta(hours=2),
            collected_at=now,
            referencia=True,
            data_mode="real",
        )
    )
    db.commit()
    resp = client.get("/v1/market/references")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["referencia"] is True and item["executable"] is False
    assert item["source"] == "frankfurter" and item["price"] == "5.4321"
    assert "Não executável" in item["note"]


def test_macro_series_include_bcb_and_fred_only(client, db):
    now = _now()
    base = dict(price=Decimal("1"), observed_at=now, captured_at=now, data_mode="real")
    db.add_all(
        [
            MarketQuote(instrument="Selic meta", label="Selic", kind="bcb_series", source="bcb", **base),
            MarketQuote(
                instrument="USD amplo (DTWEXBGS, FRED)", label="FRED", kind="fx_reference", source="fred", **base
            ),
            MarketQuote(instrument="BTC/USDT", label="BTC", kind="crypto", source="binance", **base),
        ]
    )
    db.commit()
    instruments = {r["instrument"] for r in client.get("/v1/market/macro").json()}
    assert instruments == {"Selic meta", "USD amplo (DTWEXBGS, FRED)"}


def test_triangles_empty_without_positions(client):
    resp = client.get("/v1/market/triangles", params={"limit": 5})
    assert resp.status_code == 200 and resp.json() == []


def test_indicators_insufficient_then_ok(client, db):
    now = _now()
    start = now - timedelta(minutes=5 * 130)
    assert client.get("/v1/market/indicators", params={"instrument": "BTC/USDT"}).json()["status"] == (
        "insufficient_data"
    )
    for i in range(130):
        close = Decimal(100 + (i % 17)) + Decimal(i) / 10
        open_time = start + timedelta(minutes=5 * i)
        db.add(
            MarketCandle(
                instrument="BTC/USDT",
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=close - Decimal("0.3"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                data_mode="real",
            )
        )
    db.commit()
    app_client: TestClient = client
    app_client.app.state.read_cache.clear()
    body = app_client.get("/v1/market/indicators", params={"instrument": "BTC/USDT", "interval": "5m"}).json()
    assert body["executable"] is False
    assert body["closed_candles"] > 0
    assert body["status"] == "ok"
    assert body["rsi_14"] is not None and body["adx_14"] is not None
    assert body["as_of"] is not None


def test_indicators_reject_unknown_instrument(client):
    resp = client.get("/v1/market/indicators", params={"instrument": "XRP/USDT"})
    assert resp.status_code == 422


def test_ichimoku_publicado_e_a_nuvem_vigente_nao_a_projecao(client, db):
    """A nuvem publicada é a que vale no último fechamento (calculada 26 velas antes), não o valor do índice atual."""
    now = _now()
    start = now - timedelta(minutes=5 * 130)
    rows = []
    for i in range(130):
        close = Decimal(100 + (i % 17)) + Decimal(i) / 10
        open_time = start + timedelta(minutes=5 * i)
        rows.append((open_time, close))
        db.add(
            MarketCandle(
                instrument="BTC/USDT",
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=close - Decimal("0.3"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                data_mode="real",
            )
        )
    db.commit()
    ohlc = core.Ohlc(
        open=[c - Decimal("0.3") for _, c in rows],
        high=[c + Decimal("1") for _, c in rows],
        low=[c - Decimal("1") for _, c in rows],
        close=[c for _, c in rows],
    )
    ich = core.ichimoku(ohlc)
    last = len(rows) - 1
    body = client.get("/v1/market/indicators", params={"instrument": "BTC/USDT", "interval": "5m"}).json()
    assert body["status"] == "ok"
    assert Decimal(body["ichimoku_senkou_a"]) == ich.senkou_a[last - 26]  # type: ignore[index]
    assert Decimal(body["ichimoku_senkou_b"]) == ich.senkou_b[last - 26]  # type: ignore[index]
    assert ich.senkou_a[last] != ich.senkou_a[last - 26]  # o valor do índice atual é outro número
