"""SEC-01: each instance serves one `data_mode`. A client that declares another mode with `?data_mode=` gets
`409` and nothing is read or written, so a frontend set to «Simulação» can never feed the real dataset."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from fronteira_fx.main import create_app
from fronteira_fx.models import Account, AlertRule, JournalEntry
from tests.conftest import make_settings

ACCOUNT = {"institution": "nubank", "currency": "BRL", "balance_free": "100", "label": "x"}


def test_mutations_declaring_another_mode_are_refused_and_write_nothing(client, session_factory):
    res = client.post("/v1/accounts", params={"data_mode": "simulation"}, json=ACCOUNT)
    assert res.status_code == 409, res.text
    assert "real" in res.json()["detail"] and "simulation" in res.json()["detail"]
    res = client.post("/v1/journal", params={"data_mode": "simulation"}, json={"kind": "note", "text": "sandbox"})
    assert res.status_code == 409
    rule = {"name": "r", "kind": "quote_move", "threshold": "0.01", "params": {}, "channel": "ui"}
    assert client.post("/v1/alerts/rules", params={"data_mode": "demo"}, json=rule).status_code == 409
    with session_factory() as s:
        assert s.scalar(select(func.count(Account.id))) == 0
        assert s.scalar(select(func.count(JournalEntry.id))) == 0
        assert s.scalar(select(func.count(AlertRule.id))) == 0


def test_reads_declaring_another_mode_are_refused(client):
    for path in ("/v1/accounts", "/v1/quotes", "/v1/sources", "/v1/journal", "/v1/opportunities", "/v1/snapshot"):
        assert client.get(path, params={"data_mode": "simulation"}).status_code == 409, path
    assert client.get("/v1/stream", params={"data_mode": "simulation"}).status_code == 409


def test_matching_or_absent_mode_is_served_and_health_always_answers(client):
    res = client.post("/v1/accounts", params={"data_mode": "real"}, json=ACCOUNT)
    assert res.status_code == 201 and res.json()["data_mode"] == "real"
    assert [a["data_mode"] for a in client.get("/v1/accounts", params={"data_mode": "real"}).json()] == ["real"]
    assert len(client.get("/v1/accounts").json()) == 1
    # health is how a client discovers the instance mode: never refused
    health = client.get("/v1/health", params={"data_mode": "simulation"})
    assert health.status_code == 200 and health.json()["data_mode"] == "real"
    assert client.get("/v1/accounts", params={"data_mode": "bogus"}).status_code == 422


def test_simulation_instance_accepts_simulation_and_refuses_real():
    app = create_app(make_settings(data_mode="simulation"), mount_mcp_server=False)
    with TestClient(app) as c:
        res = c.post("/v1/accounts", params={"data_mode": "simulation"}, json=ACCOUNT)
        assert res.status_code == 201 and res.json()["data_mode"] == "simulation"
        assert c.post("/v1/accounts", params={"data_mode": "real"}, json=ACCOUNT).status_code == 409


def test_every_v1_operation_but_health_declares_the_data_mode_parameter():
    spec = create_app(make_settings(), mount_mcp_server=False).openapi()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            names = {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}
            if path == "/v1/health":
                assert "data_mode" not in names
            else:
                assert "data_mode" in names, f"{method.upper()} {path}"
