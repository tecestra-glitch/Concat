"""Alerta de oportunidade por ganho líquido: ganho ≥ limite numa moeda escolhida, confiança quoted/estimated, cooldown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from fronteira_fx.models import AlertRule
from fronteira_fx.schemas import AlertRuleCreate
from fronteira_fx.services import alerts as alerts_svc

D = Decimal
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def cycle(**overrides) -> dict:
    base = {
        "start": "BRL@cash:FOZ",
        "path": ["BRL@cash:FOZ", "USD@chaco:CDE", "BRL@cash:FOZ"],
        "gain_by_currency": {"BRL": "41.20", "USD": "7.60", "PYG": "55000"},
        "gain": "41.20",
        "roi": "0.0165",
        "minutes": "45",
        "confidence": "quoted",
        "requires_declaration": False,
    }
    base.update(overrides)
    return base


def rule(**overrides) -> AlertRule:
    base = dict(
        name="ganho líquido",
        kind="cycle_net_gain",
        threshold=D("20"),
        params={"currency": "BRL"},
        channel="ui",
        cooldown_s=0,
        enabled=True,
        data_mode="real",
        created_at=NOW,
    )
    base.update(overrides)
    return AlertRule(**base)


def ctx(*cycles: dict) -> alerts_svc.AlertContext:
    return alerts_svc.AlertContext(now=NOW, cycles=list(cycles))


def test_rule_creation_accepts_the_kind_with_currency_and_threshold():
    body = AlertRuleCreate(name="x", kind="cycle_net_gain", threshold=D("20"), params={"currency": "BRL"})
    assert body.kind == "cycle_net_gain"


@pytest.mark.parametrize("params", [None, {}, {"currency": "EUR"}])
def test_rule_creation_requires_a_known_currency(params):
    with pytest.raises(ValidationError, match="currency"):
        AlertRuleCreate(name="x", kind="cycle_net_gain", threshold=D("20"), params=params)


def test_rule_creation_requires_a_non_negative_threshold():
    with pytest.raises(ValidationError, match="threshold"):
        AlertRuleCreate(name="x", kind="cycle_net_gain", threshold=None, params={"currency": "BRL"})
    with pytest.raises(ValidationError, match="threshold"):
        AlertRuleCreate(name="x", kind="cycle_net_gain", threshold=D("-1"), params={"currency": "BRL"})


def test_fires_when_net_gain_in_the_chosen_currency_reaches_the_threshold():
    msg = alerts_svc._match_cycle_net_gain(rule(), ctx(cycle()))
    assert msg is not None
    text, payload = msg
    assert "R$ 41,20" in text and "incompleto" not in text
    assert payload["currency"] == "BRL" and payload["confidence"] == "quoted"


def test_does_not_fire_below_threshold_or_for_other_currency_gain():
    assert alerts_svc._match_cycle_net_gain(rule(threshold=D("50")), ctx(cycle())) is None
    assert alerts_svc._match_cycle_net_gain(rule(params={"currency": "USD"}, threshold=D("8")), ctx(cycle())) is None


def test_incomplete_cycles_never_fire_and_estimated_ones_do():
    assert alerts_svc._match_cycle_net_gain(rule(), ctx(cycle(confidence="incomplete"))) is None
    assert alerts_svc._match_cycle_net_gain(rule(), ctx(cycle(confidence="estimated"))) is not None


def test_null_gain_in_that_currency_never_fires():
    assert alerts_svc._match_cycle_net_gain(rule(), ctx(cycle(gain_by_currency={"BRL": None}))) is None


def test_non_positive_gain_never_fires_even_with_zero_threshold():
    assert alerts_svc._match_cycle_net_gain(rule(threshold=D("0")), ctx(cycle(gain_by_currency={"BRL": "0"}))) is None


def test_picks_the_best_cycle_for_the_message():
    best = cycle(gain_by_currency={"BRL": "90", "USD": "0", "PYG": "0"}, path=["BRL@cash:FOZ", "X", "BRL@cash:FOZ"])
    text, payload = alerts_svc._match_cycle_net_gain(rule(), ctx(cycle(), best))
    assert payload["path"] == ["BRL@cash:FOZ", "X", "BRL@cash:FOZ"]
    assert "R$ 90" in text


def test_evaluate_rules_creates_an_event_and_respects_cooldown(db):
    db.add(rule(cooldown_s=3600))
    db.flush()
    first = alerts_svc.evaluate_rules(db, ctx(cycle()), data_mode="real")
    assert len(first) == 1 and first[0].payload["currency"] == "BRL"
    later = alerts_svc.AlertContext(now=NOW + timedelta(minutes=10), cycles=[cycle()])
    assert alerts_svc.evaluate_rules(db, later, data_mode="real") == []  # dentro do cooldown
    after = alerts_svc.AlertContext(now=NOW + timedelta(hours=2), cycles=[cycle()])
    assert len(alerts_svc.evaluate_rules(db, after, data_mode="real")) == 1


def test_cycles_are_loaded_only_when_a_net_gain_rule_exists(db):
    assert alerts_svc.cycles_for_rules(db, data_mode="real") == []  # sem regra: nem calcula
    db.add(rule())
    db.flush()
    # sem cotações nem contas, o cálculo roda e devolve lista vazia (não é erro)
    assert alerts_svc.cycles_for_rules(db, data_mode="real") == []
