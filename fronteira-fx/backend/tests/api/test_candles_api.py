"""Rotas do pregão (`api/candles.py`): o router é montado só aqui, a integração registra em `api/__init__.py`."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fronteira_fx.api.candles import router
from fronteira_fx.main import create_app
from fronteira_fx.schemas_candles import CandleSeries, HouseSession, SessionStats
from fronteira_fx.services.collector import Collector
from fronteira_fx.services.quotes import store_quote_draft
from tests.conftest import add_source, draft, make_settings, seed_market

KEY = "chaco:CDE:USD/PYG:cash"
DAY = datetime(2026, 11, 2, tzinfo=UTC)
WINDOW = {"from": "2026-11-02T12:00:00Z", "to": "2026-11-02T13:00:00Z"}


def _mount(app: FastAPI) -> None:
    """Registra o router do pregão no app de teste (no-op quando a integração já o registrou)."""
    if not any(getattr(r, "path", "") == "/v1/candles" for r in app.routes):
        app.include_router(router, prefix="/v1")


def _seed_canonical(db) -> None:
    """Exemplo canônico de §0.4: 12:01, 12:06, 12:11 (só compra), 12:16 UTC."""
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde-centro", "CDE")])
    rows = [(1, "7320", "7350"), (6, "7322", "7352"), (11, "7318", None), (16, "7325", "7355")]
    for minute, buy, sell in rows:
        store_quote_draft(
            db,
            draft("chaco", "USD", "PYG", buy, sell, city="CDE"),
            evidence_id=None,
            data_mode="real",
            captured_at=DAY.replace(hour=12, minute=minute),
        )
    db.commit()


# ---- /v1/candles --------------------------------------------------------------------------------


def test_get_candles_aggregates_seeded_quotes(app, client, db):
    _mount(app)
    _seed_canonical(db)
    r = client.get("/v1/candles", params={"key": KEY, "tf": "15m", **WINDOW})
    assert r.status_code == 200, r.text
    body = r.json()
    series = CandleSeries.model_validate(body)
    assert (series.key, series.tf, series.data_mode) == (KEY, "15m", "real")
    assert len(body["candles"]) == 2
    first, second = body["candles"]
    assert first == {
        "t": "2026-11-02T12:00:00Z",
        "o": "7335",
        "h": "7337",
        "l": "7318",
        "c": "7318",
        "n": 3,
        "spread_avg": "30",
        "buy_c": "7318",
        "sell_c": "7352",
        "data_mode": "real",
    }
    assert second["t"] == "2026-11-02T12:15:00Z"
    assert (second["o"], second["h"], second["l"], second["c"], second["n"]) == ("7340", "7340", "7340", "7340", 1)
    assert (second["spread_avg"], second["buy_c"], second["sell_c"]) == ("30", "7325", "7355")

    hourly = client.get("/v1/candles", params={"key": KEY, "tf": "1h", **WINDOW}).json()
    assert len(hourly["candles"]) == 1 and hourly["candles"][0]["n"] == 4 and hourly["candles"][0]["c"] == "7340"


def test_get_candles_without_quotes_is_200_with_empty_list(app, client):
    _mount(app)
    r = client.get("/v1/candles", params={"key": "x:CDE:USD/PYG:cash", "tf": "1h"})
    assert r.status_code == 200, r.text
    assert r.json() == {"key": "x:CDE:USD/PYG:cash", "tf": "1h", "candles": [], "data_mode": "real"}


def test_get_candles_limit_cuts_the_tail(app, client, db):
    _mount(app)
    _seed_canonical(db)
    body = client.get("/v1/candles", params={"key": KEY, "tf": "15m", "limit": 1, **WINDOW}).json()
    assert [c["t"] for c in body["candles"]] == ["2026-11-02T12:15:00Z"]


def test_get_candles_validation_errors(app, client):
    _mount(app)
    assert client.get("/v1/candles", params={"key": KEY, "tf": "5m"}).status_code == 422
    assert client.get("/v1/candles", params={"key": KEY, "tf": "15m", "limit": 0}).status_code == 422
    assert client.get("/v1/candles", params={"key": KEY, "tf": "15m", "limit": 1001}).status_code == 422
    assert client.get("/v1/candles", params={"key": "", "tf": "15m"}).status_code == 422
    assert client.get("/v1/candles", params={"tf": "15m"}).status_code == 422
    assert client.get("/v1/candles", params={"key": KEY}).status_code == 422
    r = client.get(
        "/v1/candles",
        params={"key": KEY, "tf": "15m", "from": "2026-11-02T13:00:00Z", "to": "2026-11-02T12:00:00Z"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "from deve ser anterior a to"
    same = client.get(
        "/v1/candles",
        params={"key": KEY, "tf": "15m", "from": "2026-11-02T12:00:00Z", "to": "2026-11-02T12:00:00Z"},
    )
    assert same.status_code == 422 and same.json()["detail"] == "from deve ser anterior a to"


def test_get_candles_naive_dates_are_utc(app, client, db):
    _mount(app)
    _seed_canonical(db)
    r = client.get(
        "/v1/candles", params={"key": KEY, "tf": "15m", "from": "2026-11-02T12:00:00", "to": "2026-11-02T12:15:00"}
    )
    assert r.status_code == 200, r.text
    assert [c["t"] for c in r.json()["candles"]] == ["2026-11-02T12:00:00Z"]


# ---- /v1/pregao/stats ---------------------------------------------------------------------------


def test_get_pregao_stats_one_entry_per_key_in_order(app, client):
    _mount(app)
    r = client.get("/v1/pregao/stats", params={"keys": "a,b"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["key"] for s in body] == ["a", "b"]
    for item in body:
        stats = SessionStats.model_validate(item)
        assert stats.data_mode == "real"
        assert stats.n_quotes == 0 and stats.houses == 0
        assert stats.open is None and stats.last is None and stats.last_at is None and stats.change_pct is None
        assert item["day_start"].endswith("-03:00")  # 00:00 em Assunção, com offset


def test_get_pregao_stats_splits_and_strips_keys(app, client):
    _mount(app)
    r = client.get("/v1/pregao/stats", params={"keys": " a , ,b, "})
    assert r.status_code == 200, r.text
    assert [s["key"] for s in r.json()] == ["a", "b"]


def test_get_pregao_stats_validation(app, client):
    _mount(app)
    assert client.get("/v1/pregao/stats", params={"keys": ""}).status_code == 422
    assert client.get("/v1/pregao/stats").status_code == 422
    blank = client.get("/v1/pregao/stats", params={"keys": " , "})
    assert blank.status_code == 422 and blank.json()["detail"] == "keys: informe de 1 a 20 chaves"
    too_many = client.get("/v1/pregao/stats", params={"keys": ",".join(f"k{i}" for i in range(21))})
    assert too_many.status_code == 422 and too_many.json()["detail"] == "keys: informe de 1 a 20 chaves"
    ok = client.get("/v1/pregao/stats", params={"keys": ",".join(f"k{i}" for i in range(20))})
    assert ok.status_code == 200 and len(ok.json()) == 20


# ---- /v1/pregao/sessions ------------------------------------------------------------------------


def test_get_pregao_sessions_lists_sources_in_order_with_reference_flag(app, client, db):
    _mount(app)
    seed_market(db)
    r = client.get("/v1/pregao/sessions")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [s["source_id"] for s in body]
    assert ids == sorted(ids) == ["bcp", "chaco", "nomad", "ueno", "wu"]
    by_id = {s["source_id"]: HouseSession.model_validate(s) for s in body}
    assert by_id["bcp"].reference is True
    assert all(not s.reference for sid, s in by_id.items() if sid != "bcp")
    assert all(s.data_mode == "real" for s in by_id.values())
    # B6: chaco e ueno têm horário em market_hours.json (ueno é digital 24h, sempre aberta)
    assert by_id["chaco"].status in {"open", "closed", "pre"} and by_id["chaco"].tz == "America/Asuncion"
    assert by_id["ueno"].status == "open"
    # `wu` não existe em market_hours.json: sem horário, nome vem de `Source.name`, campos de horário nulos
    wu = by_id["wu"]
    assert wu.status == "unknown" and wu.name == "Wu"
    assert wu.city is None and wu.tz is None and wu.channel is None
    assert wu.opens_at is None and wu.closes_at is None and wu.next_change_at is None


def test_get_pregao_sessions_empty_without_sources(app, client):
    _mount(app)
    r = client.get("/v1/pregao/sessions")
    assert r.status_code == 200 and r.json() == []


# ---- modo demo: nunca toca o banco --------------------------------------------------------------


def test_demo_mode_uses_generators_not_the_database():
    app = create_app(make_settings(data_mode="demo"))
    app.state.collector = Collector(app.state.session_factory, app.state.settings, adapters={})
    _mount(app)
    with TestClient(app) as c:
        candles = c.get("/v1/candles", params={"key": KEY, "tf": "1h", "limit": 5})
        assert candles.status_code == 200, candles.text
        body = candles.json()
        assert body["data_mode"] == "demo" and body["key"] == KEY and body["tf"] == "1h"
        assert len(body["candles"]) == 5  # gerador demo (B3): 5 velas
        assert all(cndl["data_mode"] == "demo" for cndl in body["candles"])

        stats = c.get("/v1/pregao/stats", params={"keys": "k"})
        assert stats.status_code == 200, stats.text
        assert len(stats.json()) == 1
        assert stats.json()[0]["key"] == "k" and stats.json()[0]["data_mode"] == "demo"
        assert SessionStats.model_validate(stats.json()[0]).day_start.utcoffset().total_seconds() == -3 * 3600

        sessions = c.get("/v1/pregao/sessions")
        assert sessions.status_code == 200, sessions.text
        assert len(sessions.json()) == 7  # gerador demo (B3): uma sessão por casa demo
        assert [s["source_id"] for s in sessions.json() if s["reference"]] == ["demo-bcp"]
        assert all(s["data_mode"] == "demo" for s in sessions.json())


def test_default_demo_app_serves_the_three_pregao_routes_without_mount():
    """Integração: sem `_mount`, o app padrão em modo demo já responde às três rotas do pregão."""
    app = create_app(make_settings(data_mode="demo"))
    app.state.collector = Collector(app.state.session_factory, app.state.settings, adapters={})
    calls = (
        ("/v1/candles", {"key": KEY, "tf": "15m", "limit": 3}),
        ("/v1/pregao/stats", {"keys": KEY}),
        ("/v1/pregao/sessions", {}),
    )
    with TestClient(app) as c:
        for path, params in calls:
            res = c.get(path, params=params)
            assert res.status_code == 200, f"{path}: {res.status_code} {res.text}"
            body = res.json()
            rows = body["candles"] if path == "/v1/candles" else body
            assert rows, path
            assert all(row["data_mode"] == "demo" for row in rows), path


# ---- registro -----------------------------------------------------------------------------------


def test_router_is_registered_in_the_default_app(app):
    paths = app.openapi()["paths"]
    assert "/v1/candles" in paths
    assert "/v1/pregao/stats" in paths and "/v1/pregao/sessions" in paths
    assert "/v1/history" in paths  # o app continua inteiro


def test_router_declares_operation_ids_and_tag():
    ops = {getattr(r, "operation_id", None): getattr(r, "path", "") for r in router.routes}
    assert ops == {
        "get_candles": "/candles",
        "get_pregao_stats": "/pregao/stats",
        "get_pregao_sessions": "/pregao/sessions",
    }
    assert all("pregao" in getattr(r, "tags", []) for r in router.routes)
