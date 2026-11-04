"""Rotas de planos de execução: criam a partir de um ciclo atual, exigem API key para escrever, nunca executam."""

from __future__ import annotations

from datetime import timedelta

from fronteira_fx.models import Account, utcnow
from fronteira_fx.services.quotes import store_quote_draft
from tests.conftest import add_source, draft, seed_market


def _seed_profitable_cash(db, *, age: timedelta = timedelta(0), houses_in_foz: bool = False) -> None:
    """Duas casas em CDE com spread cruzado (comprar USD barato numa, vender caro na outra): um ciclo com ganho
    positivo que não depende do ueno (descontinuado, fora do grafo)."""
    add_source(db, "casa_a", kind="exchange_house", cities=["CDE"], branches=[("casa-a-cde", "CDE")])
    add_source(db, "casa_b", kind="exchange_house", cities=["CDE"], branches=[("casa-b-cde", "CDE")])
    drafts = [
        draft("casa_a", "USD", "BRL", "5.20", "5.30", kind="executable", city="CDE", branch_id="casa-a-cde"),
        draft("casa_b", "USD", "BRL", "5.50", "5.60", kind="executable", city="CDE", branch_id="casa-b-cde"),
    ]
    if houses_in_foz:  # casa de FOZ: cruzar a fronteira na volta (ciclo de 9 nós com balcão nas duas pontas)
        add_source(db, "casa_c", kind="exchange_house", cities=["FOZ"], branches=[("casa-c-foz", "FOZ")])
        drafts[1] = draft("casa_c", "USD", "BRL", "5.50", "5.60", kind="executable", city="FOZ", branch_id="casa-c-foz")
    now = utcnow() - age
    for i, d in enumerate(drafts):
        store_quote_draft(db, d, evidence_id=None, data_mode="real", captured_at=now - timedelta(seconds=i))
    db.add(
        Account(
            institution="carteira",
            label="carteira BRL",
            currency="BRL",
            kind="cash",
            location="CDE",
            balance_free=10000,
            balance_reserved=0,
            balance_in_transit=0,
            data_mode="real",
        )
    )
    db.commit()


def _seed_parked_balance(db) -> None:
    seed_market(db, now=utcnow())
    _seed_profitable_cash(db)
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
    cycles = client.get("/v1/opportunities/cycles", params={"max_len": 4, "mode": "todos"}).json()
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


def test_plan_out_keeps_unknown_costs_as_null_not_zero():
    from fronteira_fx.api.plans import _costs

    assert _costs({"spread": "0", "fees": None, "iof": "0", "transport": "12.5"}) == {
        "spread": "0",
        "fees": None,
        "iof": "0",
        "transport": "12.5",
    }
    assert _costs(None) is None


def test_plan_from_quotes_older_than_the_limit_is_born_expired_and_cannot_be_approved(client, db):
    _seed_profitable_cash(db, age=timedelta(days=3))
    cycle = next(c for c in client.get("/v1/opportunities/cycles", params={"max_len": 4, "mode": "todos"}).json() if c["gain"] != "0")
    r = client.post("/v1/plans", json={"start": cycle["start"], "path": cycle["path"]})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "expired"
    assert client.post(f"/v1/plans/{r.json()['id']}/approve").status_code == 409


def test_every_cycle_listed_by_the_api_can_become_a_plan_even_with_a_long_path(client, db):
    # casa em CDE e casa em FOZ com carteira em CDE: a volta por balcão nas duas pontas faz 9 nós em 4 pernas
    _seed_profitable_cash(db, houses_in_foz=True)
    cycles = client.get("/v1/opportunities/cycles", params={"max_len": 4, "limit": 500, "mode": "todos"}).json()
    long = [c for c in cycles if len(c["path"]) > 7 and float(c["gain"]) > 0]
    assert long, "o cenário precisa de um ciclo lucrativo com mais de 7 nós"
    r = client.post("/v1/plans", json={"start": long[0]["start"], "path": long[0]["path"]})
    assert r.status_code == 201, r.text
