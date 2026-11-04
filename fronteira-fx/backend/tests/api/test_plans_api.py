"""Rotas de planos de execução: criam a partir de um ciclo atual, exigem API key para escrever, nunca executam."""

from __future__ import annotations

from fronteira_fx.models import Account
from tests.conftest import seed_market


def _seed_parked_balance(db) -> None:
    seed_market(db)
    db.add(
        Account(
            institution="nubank",
            label="Nubank BRL",
            currency="BRL",
            kind="bank",
            location="digital",
            balance_free=1000,
            balance_reserved=0,
            balance_in_transit=0,
            data_mode="real",
        )
    )
    db.commit()


def _first_cycle(client) -> dict:
    cycles = client.get("/v1/opportunities/cycles", params={"max_len": 4}).json()
    assert cycles, "a market with parked balances must yield cycles"
    return cycles[0]


def test_plan_from_a_cycle_is_proposed_with_pt_br_steps_and_no_execution(client, db):
    _seed_parked_balance(db)
    cycle = _first_cycle(client)
    r = client.post("/v1/plans", json={"start": cycle["start"], "path": cycle["path"]})
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "proposed" and plan["data_mode"] == "real"
    assert plan["steps"] and all(s["status"] == "pending" for s in plan["steps"])
    assert all(isinstance(s["text"], str) and s["text"] for s in plan["steps"])
    assert isinstance(plan["amount_in"], str) and isinstance(plan["gain_expected"], str)
    assert plan["steps"][0]["channel"] in {"presencial", "assistida", "automatizavel"}
    assert {s["kind"] for s in plan["steps"]} <= {"exchange", "transfer", "travel", "deposit", "withdraw"}


def test_creating_a_plan_for_a_cycle_that_does_not_exist_is_404(client, db):
    _seed_parked_balance(db)
    r = client.post("/v1/plans", json={"start": "BRL@nubank", "path": ["BRL@nubank", "XXX@nowhere", "BRL@nubank"]})
    assert r.status_code == 404


def test_path_must_have_at_least_two_nodes(client):
    r = client.post("/v1/plans", json={"start": "BRL@nubank", "path": ["BRL@nubank"]})
    assert r.status_code == 422


def test_approve_reject_and_list(client, db):
    _seed_parked_balance(db)
    cycle = _first_cycle(client)
    plan_id = client.post("/v1/plans", json={"start": cycle["start"], "path": cycle["path"]}).json()["id"]
    r = client.post(f"/v1/plans/{plan_id}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_at"]
    assert client.post(f"/v1/plans/{plan_id}/approve").status_code == 409
    listed = client.get("/v1/plans").json()
    assert [p["id"] for p in listed] == [plan_id]
    assert client.get(f"/v1/plans/{plan_id}").json()["status"] == "approved"
    assert client.get("/v1/plans/nope").status_code == 404
    # antes de qualquer execução o dono pode recusar mesmo aprovado
    r = client.post(f"/v1/plans/{plan_id}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.post(f"/v1/plans/{plan_id}/approve").status_code == 409


def test_steps_in_order_then_result_goes_to_the_journal(client, db):
    _seed_parked_balance(db)
    cycle = _first_cycle(client)
    plan = client.post("/v1/plans", json={"start": cycle["start"], "path": cycle["path"]}).json()
    pid = plan["id"]
    client.post(f"/v1/plans/{pid}/approve")
    n_steps = len(plan["steps"])
    assert client.post(f"/v1/plans/{pid}/steps/2/done", json={"actual_out": "1"}).status_code == 409
    for n in range(1, n_steps + 1):
        r = client.post(f"/v1/plans/{pid}/steps/{n}/done", json={"actual_out": "10", "note": f"passo {n}"})
        assert r.status_code == 200, r.text
    final = client.get(f"/v1/plans/{pid}").json()
    assert final["status"] == "done" and final["completed_at"]
    assert all(s["status"] == "done" for s in final["steps"])
    journal = client.get("/v1/journal").json()
    results = [e for e in journal if e["kind"] == "result"]
    assert len(results) == 1 and "esperado" in results[0]["text"] and "realizado" in results[0]["text"]


def test_bad_actual_out_is_rejected(client, db):
    _seed_parked_balance(db)
    cycle = _first_cycle(client)
    pid = client.post("/v1/plans", json={"start": cycle["start"], "path": cycle["path"]}).json()["id"]
    client.post(f"/v1/plans/{pid}/approve")
    assert client.post(f"/v1/plans/{pid}/steps/1/done", json={"actual_out": "-3"}).status_code == 422
    assert client.post(f"/v1/plans/{pid}/steps/1/done", json={"actual_out": 10.5}).status_code == 422
