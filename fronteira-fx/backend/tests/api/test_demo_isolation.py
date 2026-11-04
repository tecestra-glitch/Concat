from fastapi.testclient import TestClient

from fronteira_fx.services.demo import seed_demo
from tests.conftest import make_settings, seed_market


def test_demo_rows_are_invisible_in_real_mode(client, db):
    seed_demo(db)
    db.commit()
    assert client.get("/v1/health").json()["data_mode"] == "real"
    assert client.get("/v1/sources").json() == []
    assert client.get("/v1/quotes").json() == []
    assert client.get("/v1/accounts").json() == []
    assert client.get("/v1/opportunities").json() == []
    assert client.get("/v1/evidence").json() == []
    assert client.get("/v1/journal").json() == []
    snap = client.get("/v1/snapshot").json()
    assert snap["quotes"] == [] and snap["sources"] == [] and snap["opportunities"] == []
    assert client.get("/v1/sources/chaco/branches").status_code == 404
    sim = client.post("/v1/simulations/routes", json={"capital_brl": "5000"}).json()
    assert sim["opportunities"] == []


def test_demo_mode_serves_only_demo_rows_and_labels_them():
    from fronteira_fx.main import create_app

    app = create_app(make_settings(data_mode="demo"))
    with TestClient(app) as c:
        health = c.get("/v1/health").json()
        assert health["data_mode"] == "demo"
        sources = c.get("/v1/sources").json()
        assert sources and all(s["data_mode"] == "demo" and "(demo)" in s["name"] for s in sources)
        quotes = c.get("/v1/quotes").json()
        assert quotes and all(q["data_mode"] == "demo" for q in quotes)
        assert {q["city"] for q in quotes if q["city"]} == {"CDE", "ASU", "PJC"}
        accounts = c.get("/v1/accounts").json()
        assert {a["institution"] for a in accounts} >= {"banco_py", "nomad", "revolut"}
        opps = c.get("/v1/opportunities", params={"capital": "5000"}).json()
        assert opps and all(o["data_mode"] == "demo" for o in opps)
        # real rows added to the same DB stay invisible in demo mode
        with app.state.session_factory() as s:
            seed_market(s, data_mode="real")
        assert all(src["data_mode"] == "demo" for src in c.get("/v1/sources").json())
        assert all(q["data_mode"] == "demo" for q in c.get("/v1/quotes").json())


def test_seed_demo_is_idempotent(db):
    first = seed_demo(db)
    assert first["sources"] == 7 and first["quotes"] > 0 and first["opportunities"] > 0 and first["events"] > 0
    assert seed_demo(db) == {k: 0 for k in first}


def test_fx_seed_demo_seeds_only_when_db_empty():
    from fronteira_fx.main import create_app

    app = create_app(make_settings(seed_demo=True, data_mode="real"))
    with TestClient(app) as c:
        # seeded demo rows exist in the DB but the server is in real mode => invisible
        assert c.get("/v1/sources").json() == []
        with app.state.session_factory() as s:
            from fronteira_fx.services.demo import demo_present

            assert demo_present(s)
