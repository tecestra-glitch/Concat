"""Planos de execução (fase A): organizam os passos de um ciclo. Nada aqui executa movimentação financeira."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from fronteira_fx.models import ExecutionPlan, JournalEntry
from fronteira_fx.services import plans as plans_svc
from fronteira_fx.services.plans import PlanError

D = Decimal
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def leg(**overrides) -> dict:
    base = {
        "kind": "exchange",
        "channel": "presencial",
        "from": "PYG@chaco:CDE",
        "to": "USD@chaco:CDE",
        "via": "chaco cash @CDE (venda 7300)",
        "minutes": 15,
        "border": False,
        "amount_in": "7300000",
        "amount_out": "1000",
        "costs": {"currency": "PYG", "spread": "0", "fees": "0", "iof": "0", "transport": "0"},
    }
    base.update(overrides)
    return base


def cycle_dict() -> dict:
    legs = [
        leg(
            kind="travel",
            **{"from": "BRL@cash:FOZ", "to": "BRL@cash:CDE", "via": "deslocamento FOZ→CDE (car)", "minutes": 40},
            border=True,
            amount_in="10000",
            amount_out="10000",
        ),
        leg(),
        leg(kind="withdraw", **{"from": "USD@chaco:CDE", "to": "USD@cash:CDE"}, amount_in="1000", amount_out="1000"),
    ]
    return {
        "start": "PYG@cash:CDE",
        "path": ["PYG@cash:CDE", "PYG@chaco:CDE", "USD@chaco:CDE", "USD@cash:CDE"],
        "edges": [{"evidence_id": None, "quoted_at": NOW.isoformat(), "via": "chaco cash @CDE (venda 7300)",
                   "rate": "0.00013"}],
        "legs": legs,
        "amount_in": "7300000",
        "amount_out": "7400000",
        "gain": "100000",
        "roi": "0.0137",
        "gain_by_currency": {"BRL": "70", "USD": "13.7", "PYG": "100000"},
        "costs": {"spread": "0", "fees": "0", "iof": "0", "transport": "0"},
        "requires_declaration": False,
        "minutes": 55,
        "confidence": "quoted",
        "data_mode": "real",
    }


def test_steps_are_written_in_portuguese_and_name_the_place():
    steps = plans_svc.build_steps(cycle_dict())
    texts = [s["text"] for s in steps]
    assert texts[0] == "Leve o dinheiro de FOZ para CDE (≈ 40 min)"
    assert texts[1] == "Compre 1.000 USD na Cambios Chaco (CDE) pagando 7.300.000 PYG (cotação: 1 USD = 7.300 PYG)"
    assert texts[2] == "Retire 1.000 USD de Cambios Chaco (CDE)"
    assert [s["n"] for s in steps] == [1, 2, 3]
    assert steps[0]["status"] == "pending" and steps[0]["channel"] == "presencial"


def test_price_is_written_in_the_house_convention_and_never_rounds_to_zero():
    # comprar PYG com BRL: o preço é 1 BRL = 1.300 PYG (antes saía "a 0,00 BRL")
    buy_pyg = plans_svc.leg_text(
        leg(**{"from": "BRL@chaco:CDE", "to": "PYG@chaco:CDE", "amount_in": "1000", "amount_out": "1300000"})
    )
    assert "a 0,00" not in buy_pyg and "(cotação: 1 BRL = 1.300 PYG)" in buy_pyg
    # vender USD por BRL: o preço é 1 USD = 5,40 BRL (antes saía "a 0,19 USD", que dá a entender 5,26)
    sell_usd = plans_svc.leg_text(
        leg(**{"from": "USD@chaco:CDE", "to": "BRL@chaco:CDE", "amount_in": "1000", "amount_out": "5400"})
    )
    assert sell_usd == "Compre 5.400 BRL na Cambios Chaco (CDE) pagando 1.000 USD (cotação: 1 USD = 5,40 BRL)"


def test_converting_transfer_says_what_leaves_and_what_arrives():
    text = plans_svc.leg_text(
        leg(
            kind="transfer",
            channel="assistida",
            **{"from": "BRL@brbank", "to": "USD@nomad"},
            via="conversão brbank→nomad",
            minutes=60,
            amount_in="5000",
            amount_out="920",
        )
    )
    assert text == "Envie 5.000 BRL de banco brasileiro e receba ≈ 920 USD em Nomad (≈ 60 min)"


def test_same_currency_transfer_keeps_the_simple_wording():
    text = plans_svc.leg_text(
        leg(kind="transfer", channel="assistida", **{"from": "USD@nomad", "to": "USD@revolut"}, minutes=60,
            amount_in="1000", amount_out="1000")
    )
    assert text == "Transfira 1.000 USD de Nomad para Revolut (≈ 60 min)"


def test_bank_ids_have_readable_names():
    assert plans_svc.place_name("nubank") == "Nubank"
    assert plans_svc.place_name("banco_py") == "banco paraguaio"
    assert plans_svc.place_name("itau") == "Itaú"


def test_money_in_steps_is_a_decimal_string_pt_br_without_float_noise():
    text = plans_svc.money_text(D("1234.5"), "USD")
    assert text == "1.234,50 USD"
    assert plans_svc.money_text(D("7300000"), "PYG") == "7.300.000 PYG"


def test_create_plan_snapshots_the_cycle_and_starts_proposed(db):
    plan = plans_svc.create_plan(
        db, cycles=[cycle_dict()], start="PYG@cash:CDE", path=cycle_dict()["path"], data_mode="real", now=NOW, max_age_s=900
    )
    assert plan.status == "proposed"
    assert plan.amount_in == D("7300000") and plan.gain_expected == D("100000")
    assert plan.snapshot["legs"][1]["from"] == "PYG@chaco:CDE"
    assert plan.quotes_as_of == NOW  # sem evidência de cotação: a idade parte do momento do plano
    assert len(plan.steps) == 3 and all(s.status == "pending" for s in plan.steps)


def test_create_plan_refuses_a_cycle_that_loses_money(db):
    losing = {**cycle_dict(), "gain": "-4.26", "amount_out": "6.74", "gain_by_currency": {"BRL": "-1", "USD": "-1", "PYG": "-1"}}
    with pytest.raises(PlanError) as exc:
        plans_svc.create_plan(
            db, cycles=[losing], start="PYG@cash:CDE", path=cycle_dict()["path"], data_mode="real", now=NOW, max_age_s=900
        )
    assert exc.value.status == 422
    assert db.scalar(select(ExecutionPlan.id).limit(1)) is None


def test_create_plan_refuses_a_cycle_without_positive_gain(db):
    zero = {**cycle_dict(), "gain": "0"}
    with pytest.raises(PlanError) as exc:
        plans_svc.create_plan(db, cycles=[zero], start="PYG@cash:CDE", path=cycle_dict()["path"], data_mode="real", now=NOW, max_age_s=900)
    assert exc.value.status == 422


def test_create_plan_refuses_a_cycle_that_is_not_there(db):
    with pytest.raises(PlanError) as exc:
        plans_svc.create_plan(db, cycles=[], start="PYG@cash:CDE", path=["PYG@cash:CDE", "X"], data_mode="real", now=NOW, max_age_s=900)
    assert exc.value.status == 404


def make_plan(db, now: datetime = NOW) -> ExecutionPlan:
    return plans_svc.create_plan(
        db, cycles=[cycle_dict()], start="PYG@cash:CDE", path=cycle_dict()["path"], data_mode="real", now=now, max_age_s=900
    )


def test_approve_only_records_the_decision(db):
    plan = make_plan(db)
    plans_svc.approve(db, plan, now=NOW + timedelta(seconds=10))
    assert plan.status == "approved" and plan.decided_at == NOW + timedelta(seconds=10)
    with pytest.raises(PlanError) as exc:
        plans_svc.approve(db, plan, now=NOW)
    assert exc.value.status == 409
    assert db.scalars(select(JournalEntry)).all() == []  # aprovar não registra nada no diário


def test_reject_closes_the_plan_and_blocks_approval(db):
    plan = make_plan(db)
    plans_svc.reject(db, plan, now=NOW)
    assert plan.status == "rejected"
    with pytest.raises(PlanError):
        plans_svc.approve(db, plan, now=NOW)


def test_plan_expires_when_its_oldest_quote_passes_the_limit(db):
    plan = make_plan(db)
    later = NOW + timedelta(seconds=901)
    assert plans_svc.refresh_status(plan, now=later) == "expired"
    assert plan.status == "expired"
    with pytest.raises(PlanError) as exc:
        plans_svc.approve(db, plan, now=later)
    assert exc.value.status == 409


def test_expiry_stops_once_execution_started(db):
    plan = make_plan(db)
    plans_svc.approve(db, plan, now=NOW)
    plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note=None, now=NOW + timedelta(minutes=1))
    assert plans_svc.refresh_status(plan, now=NOW + timedelta(days=3)) == "in_progress"


def test_steps_must_be_done_in_order_and_only_once(db):
    plan = make_plan(db)
    plans_svc.approve(db, plan, now=NOW)
    with pytest.raises(PlanError) as exc:
        plans_svc.mark_step_done(db, plan, 2, actual_out=D("1"), note=None, now=NOW)
    assert exc.value.status == 409
    plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note="ok", now=NOW)
    assert plan.status == "in_progress"
    with pytest.raises(PlanError):
        plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note=None, now=NOW)


def test_steps_need_an_approved_plan(db):
    plan = make_plan(db)
    with pytest.raises(PlanError):
        plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note=None, now=NOW)


def test_completing_all_steps_records_expected_versus_realized_in_the_journal(db):
    plan = make_plan(db)
    plans_svc.approve(db, plan, now=NOW)
    plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note=None, now=NOW)
    plans_svc.mark_step_done(db, plan, 2, actual_out=D("1000"), note=None, now=NOW)
    plans_svc.mark_step_done(db, plan, 3, actual_out=D("7350000"), note="casa pagou um pouco menos", now=NOW)
    assert plan.status == "done" and plan.completed_at == NOW
    (entry,) = db.scalars(select(JournalEntry)).all()
    assert entry.kind == "result"
    assert [a["label"] for a in entry.amounts] == ["esperado", "realizado"]  # esperado × realizado
    assert [a["amount"] for a in entry.amounts] == ["7400000", "7350000"]
    assert "esperado 7.400.000 PYG" in entry.text and "realizado 7.350.000 PYG" in entry.text
    assert entry.data_mode == "real"


def test_done_step_keeps_the_realized_amount_and_note(db):
    plan = make_plan(db)
    plans_svc.approve(db, plan, now=NOW)
    plans_svc.mark_step_done(db, plan, 1, actual_out=D("40"), note="trânsito rápido", now=NOW)
    step = plan.steps[0]
    assert step.status == "done" and step.actual_out == D("40") and step.note == "trânsito rápido"
    assert step.done_at == NOW


# --- SC-1: a validade do plano sai da cotação mais velha, com ou sem evidência ----------------------------------------


def test_expiry_uses_the_oldest_quote_date_even_without_evidence(db):
    c = cycle_dict()
    c["edges"] = [
        {"evidence_id": None, "via": "casa", "rate": "0.00013", "quoted_at": "2026-11-01T12:00:00+00:00"},
        {"evidence_id": None, "via": "outra", "rate": "1", "quoted_at": "2026-11-04T11:59:00+00:00"},
    ]
    plan = plans_svc.create_plan(
        db, cycles=[c], start=c["start"], path=c["path"], data_mode="real", now=NOW, max_age_s=900
    )
    assert plan.quotes_as_of == datetime(2026, 11, 1, 12, tzinfo=UTC)  # não "agora"
    assert plans_svc.refresh_status(plan, now=NOW) == "expired"


def test_a_cycle_with_no_quote_date_is_refused_instead_of_using_now(db):
    c = cycle_dict()
    c["edges"] = []  # nenhuma aresta datada: não há como provar que a cotação é recente
    with pytest.raises(PlanError) as err:
        plans_svc.create_plan(db, cycles=[c], start=c["start"], path=c["path"], data_mode="real", now=NOW, max_age_s=900)
    assert err.value.status == 422
