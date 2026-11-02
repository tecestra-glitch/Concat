from __future__ import annotations

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from fronteira_fx.notify.rules import AlertRulePatch, AlertState, evaluate, merge_rule, quote_value
from tests.notify.support import (
    D,
    NOW,
    change_payload,
    cycle_payload,
    make_rule,
    opportunity_payload,
    quote_payload,
    source_payload,
)

# --- cycle_roi -------------------------------------------------------------------------------


def test_cycle_roi_fires_at_threshold_and_not_below():
    rule = make_rule(threshold=D("0.002"))
    state = AlertState()
    at_boundary = evaluate(rule, "cycle.found", cycle_payload(roi=0.002), state, now=NOW)
    assert at_boundary is not None
    assert at_boundary.rule_id == "r1" and at_boundary.channel == "ui" and at_boundary.delivered is False

    below = evaluate(make_rule(id="r2", threshold=D("0.002")), "cycle.found", cycle_payload(roi=0.00199), AlertState(), now=NOW)
    assert below is None


def test_cycle_roi_message_is_pt_br_and_concise():
    event = evaluate(make_rule(), "cycle.found", cycle_payload(), AlertState(), now=NOW)
    assert event is not None
    assert event.message == (
        "Ciclo BRL@brbank → PYG@ueno → USD@ueno → BRL@brbank: +R$ 41,20 (0,165 %) em 3,0 d"
    )


def test_cycle_incomplete_confidence_is_flagged():
    event = evaluate(make_rule(), "cycle.found", cycle_payload(confidence="incomplete"), AlertState(), now=NOW)
    assert event is not None and event.message.endswith("incompleto (há custo pendente)")


def test_cycle_roi_ignores_other_event_types():
    assert evaluate(make_rule(), "quote.updated", cycle_payload(), AlertState(), now=NOW) is None


def test_cycle_roi_start_filter_matches_currency_prefix():
    rule = make_rule(params={"start": "PYG"})
    assert evaluate(rule, "cycle.found", cycle_payload(), AlertState(), now=NOW) is None
    rule_brl = make_rule(params={"start": "BRL"})
    assert evaluate(rule_brl, "cycle.found", cycle_payload(), AlertState(), now=NOW) is not None


def test_cycle_payload_is_json_safe_and_keeps_contract_fields():
    event = evaluate(make_rule(), "cycle.found", cycle_payload(), AlertState(), now=NOW)
    assert event is not None
    assert json.loads(json.dumps(event.payload))["path"][0] == "BRL@brbank"
    assert event.ts == NOW


def test_malformed_payload_returns_none_instead_of_raising():
    bad = {"roi": "abc", "path": None}
    assert evaluate(make_rule(), "cycle.found", bad, AlertState(), now=NOW) is None
    assert evaluate(make_rule(), "cycle.found", {"roi": True}, AlertState(), now=NOW) is None


# --- cooldown and dedupe ---------------------------------------------------------------------


def test_cooldown_suppresses_repeat_then_releases_at_exactly_cooldown_s():
    rule = make_rule(cooldown_s=600)
    state = AlertState()
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW) is not None
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW + timedelta(seconds=599)) is None
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW + timedelta(seconds=600)) is not None


def test_cooldown_is_per_cycle_not_per_rule():
    rule = make_rule(cooldown_s=600)
    state = AlertState()
    first = cycle_payload(path=["BRL@brbank", "PYG@ueno", "BRL@brbank"])
    second = cycle_payload(path=["BRL@brbank", "USD@ueno", "BRL@brbank"])
    assert evaluate(rule, "cycle.found", first, state, now=NOW) is not None
    assert evaluate(rule, "cycle.found", second, state, now=NOW) is not None  # outro ciclo: dispara
    assert evaluate(rule, "cycle.found", first, state, now=NOW + timedelta(seconds=1)) is None  # mesmo: suprime


def test_cooldown_zero_never_suppresses():
    rule = make_rule(cooldown_s=0)
    state = AlertState()
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW) is not None
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW) is not None


def test_forget_rule_clears_cooldown_and_observations():
    rule = make_rule(cooldown_s=600)
    state = AlertState()
    evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW)
    state.forget_rule(rule.id)
    assert evaluate(rule, "cycle.found", cycle_payload(), state, now=NOW) is not None


# --- quote_move ------------------------------------------------------------------------------


def _quote_rule(threshold: str = "0.002", **overrides):
    fields = {
        "id": "q1",
        "kind": "quote_move",
        "threshold": D(threshold),
        "params": {"pair": "USD/PYG", "city": "CDE"},
        "cooldown_s": 0,
    }
    fields.update(overrides)
    return make_rule(**fields)


def test_quote_move_first_observation_sets_baseline_only():
    assert evaluate(_quote_rule(), "quote.updated", quote_payload("1000", "1000"), AlertState(), now=NOW) is None


def test_quote_move_fires_exactly_at_threshold_ratio():
    rule = _quote_rule("0.002")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    event = evaluate(rule, "quote.updated", quote_payload("1002", "1002"), state, now=NOW)  # move = 0.002
    assert event is not None
    assert event.message == "USD/PYG em CDE (chaco): 1.000 → 1.002 PYG por 1 USD (+0,200 %)"


def test_quote_move_below_threshold_does_not_fire():
    rule = _quote_rule("0.002")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    assert evaluate(rule, "quote.updated", quote_payload("1001.99", "1001.99"), state, now=NOW) is None


def test_quote_move_downward_move_fires_on_absolute_ratio():
    rule = _quote_rule("0.002")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    event = evaluate(rule, "quote.updated", quote_payload("998", "998"), state, now=NOW)  # -0.002
    assert event is not None and "(-0,200 %)" in event.message


def test_quote_move_compares_with_last_observation_not_first():
    rule = _quote_rule("0.002")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    evaluate(rule, "quote.updated", quote_payload("1001", "1001"), state, now=NOW)  # 0.001: não dispara
    # de 1001 para 1003: 0.001998 -> ainda abaixo do limiar, mesmo que 1000->1003 seja 0.003
    assert evaluate(rule, "quote.updated", quote_payload("1003", "1003"), state, now=NOW) is None


def test_quote_move_zero_threshold_never_fires_on_unchanged_quote():
    rule = _quote_rule("0")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    assert evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW) is None


def test_quote_move_ignores_other_city_pair_and_source_series():
    rule = _quote_rule("0.002")
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000", city="CDE"), state, now=NOW)
    # outra cidade, outro par e outra fonte não mexem na referência de CDE/chaco
    assert evaluate(rule, "quote.updated", quote_payload("2000", "2000", city="ASU"), state, now=NOW) is None
    assert evaluate(rule, "quote.updated", quote_payload("2000", "2000", base="BRL"), state, now=NOW) is None
    assert evaluate(rule, "quote.updated", quote_payload("1002", "1002", source="ueno"), state, now=NOW) is None
    assert evaluate(rule, "quote.updated", quote_payload("1002", "1002", city="CDE"), state, now=NOW) is not None


def test_quote_move_cooldown_applies_per_series():
    rule = _quote_rule("0.002", cooldown_s=600)
    state = AlertState()
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW)
    assert evaluate(rule, "quote.updated", quote_payload("1002", "1002"), state, now=NOW) is not None
    evaluate(rule, "quote.updated", quote_payload("1000", "1000"), state, now=NOW + timedelta(seconds=10))
    assert evaluate(rule, "quote.updated", quote_payload("1002", "1002"), state, now=NOW + timedelta(seconds=20)) is None


def test_quote_value_is_midpoint_or_available_side():
    assert quote_value({"buy": "1000", "sell": "1002"}) == D("1001")
    assert quote_value({"buy": None, "sell": "1002"}) == D("1002")
    assert quote_value({"buy": "0", "sell": None}) is None
    assert quote_value({"buy": None, "sell": None}) is None


# --- source_down -----------------------------------------------------------------------------


def _source_rule(**overrides):
    return make_rule(id="s1", kind="source_down", threshold=D("0"), cooldown_s=0, **overrides)


def test_source_down_fires_only_on_transition_to_bad_health():
    rule = _source_rule()
    state = AlertState()
    assert evaluate(rule, "source.health", source_payload(health="ok"), state, now=NOW) is None
    event = evaluate(rule, "source.health", source_payload(health="blocked", last_error="captcha"), state, now=NOW)
    assert event is not None
    assert event.message == "Fonte Cambios Chaco (chaco) bloqueada. Detalhe: captcha"
    assert evaluate(rule, "source.health", source_payload(health="blocked"), state, now=NOW) is None  # já estava ruim
    assert evaluate(rule, "source.health", source_payload(health="ok"), state, now=NOW) is None  # recuperou
    assert evaluate(rule, "source.health", source_payload(health="error"), state, now=NOW) is not None


def test_source_down_first_observation_already_bad_fires():
    event = evaluate(_source_rule(), "source.health", source_payload(health="error"), AlertState(), now=NOW)
    assert event is not None and "com erro" in event.message


def test_source_down_from_source_change_status():
    rule = _source_rule()
    state = AlertState()
    event = evaluate(rule, "source.change", change_payload(status="error"), state, now=NOW)
    assert event is not None
    assert "Detalhe: timeout" in event.message
    assert evaluate(rule, "source.change", change_payload(status="ok"), state, now=NOW) is None


def test_source_down_source_filter():
    rule = _source_rule(params={"source": "ueno"})
    assert evaluate(rule, "source.health", source_payload("chaco", "blocked"), AlertState(), now=NOW) is None
    assert evaluate(rule, "source.health", source_payload("ueno", "blocked"), AlertState(), now=NOW) is not None


# --- opportunity_new -------------------------------------------------------------------------


def _opp_rule(threshold: str = "0", **overrides):
    return make_rule(id="o1", kind="opportunity_new", threshold=D(threshold), cooldown_s=0, **overrides)


def test_opportunity_new_fires_on_entry_to_main_ranking_only():
    rule = _opp_rule()
    state = AlertState()
    entered = evaluate(rule, "opportunity.updated", opportunity_payload(in_main=True), state, now=NOW)
    assert entered is not None
    assert entered.message.startswith("Nova oportunidade no ranking principal: Ciclo BRL→USD→BRL")
    assert evaluate(rule, "opportunity.updated", opportunity_payload(in_main=True), state, now=NOW) is None
    assert evaluate(rule, "opportunity.updated", opportunity_payload(in_main=False), state, now=NOW) is None
    assert evaluate(rule, "opportunity.updated", opportunity_payload(in_main=True), state, now=NOW) is not None


def test_opportunity_roi_threshold_is_checked_on_entry():
    rule = _opp_rule(threshold="0.01")
    state = AlertState()
    assert evaluate(rule, "opportunity.updated", opportunity_payload(roi="0.008"), state, now=NOW) is None
    # ROI sobe acima do limiar enquanto já está no ranking: conta como entrada qualificada
    assert evaluate(rule, "opportunity.updated", opportunity_payload(roi="0.01"), state, now=NOW) is not None
    assert evaluate(rule, "opportunity.updated", opportunity_payload(roi="0.02"), state, now=NOW) is None


def test_opportunity_channel_and_city_filters():
    rule = _opp_rule(params={"channel": "physical", "city": "CDE"})
    assert evaluate(rule, "opportunity.updated", opportunity_payload(channel="digital"), AlertState(), now=NOW) is None
    physical_asu = opportunity_payload(channel="physical", city="ASU")
    assert evaluate(rule, "opportunity.updated", physical_asu, AlertState(), now=NOW) is None
    physical_cde = opportunity_payload(channel="physical", city="CDE")
    assert evaluate(rule, "opportunity.updated", physical_cde, AlertState(), now=NOW) is not None


# --- validation of the contract shape --------------------------------------------------------


def test_threshold_serialises_as_decimal_string():
    rule = make_rule(threshold=D("0.002"))
    assert rule.model_dump(mode="json")["threshold"] == "0.002"
    assert rule.model_dump(mode="json")["cooldown_s"] == 600


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"channel": "telegram", "target": None}, "exige target"),
        ({"channel": "telegram", "target": "chat fx"}, "chat id"),
        ({"channel": "email", "target": "nao-e-email"}, "e-mail"),
        ({"channel": "webhook", "target": "ftp://x"}, "http"),
        ({"kind": "quote_move", "params": None, "threshold": D("0.002")}, "pair"),
        ({"kind": "quote_move", "params": {"pair": "USDPYG"}, "threshold": D("0.002")}, "pair"),
        ({"kind": "quote_move", "params": {"pair": "USD/PYG"}, "threshold": D("-0.1")}, "negativo"),
        ({"kind": "quote_move", "params": {"pair": "USD/PYG", "city": "XXX"}, "threshold": D("0.1")}, "city"),
        ({"cooldown_s": -1}, "cooldown_s"),
        ({"name": "   "}, "name"),
        ({"threshold": D("NaN")}, "finite"),
    ],
)
def test_rule_validation_rejects_bad_shapes(overrides, fragment):
    from fronteira_fx.notify.rules import AlertRuleIn

    data = {"name": "x", "kind": "cycle_roi", "threshold": D("0.002"), "channel": "ui"}
    data.update(overrides)
    with pytest.raises(ValidationError) as info:
        AlertRuleIn.model_validate(data)
    assert fragment in str(info.value)


def test_valid_telegram_targets_accepted():
    from fronteira_fx.notify.rules import AlertRuleIn

    for target in ("123456789", "-1001234567890", "@canal_fx"):
        rule = AlertRuleIn.model_validate(
            {"name": "x", "kind": "cycle_roi", "threshold": "0.002", "channel": "telegram", "target": target}
        )
        assert rule.target == target


def test_ui_rule_drops_target_and_extra_fields_are_rejected():
    from fronteira_fx.notify.rules import AlertRuleIn

    rule = AlertRuleIn.model_validate({"name": "x", "kind": "cycle_roi", "threshold": "0.002", "target": "algo"})
    assert rule.target is None
    with pytest.raises(ValidationError):
        AlertRuleIn.model_validate({"name": "x", "kind": "cycle_roi", "threshold": "0.002", "surprise": 1})


def test_merge_rule_applies_patch_and_revalidates():
    rule = make_rule(id="keep", threshold=D("0.002"))
    merged = merge_rule(rule, AlertRulePatch(threshold=D("0.005"), enabled=False))
    assert merged.id == "keep" and merged.threshold == D("0.005") and merged.enabled is False
    with pytest.raises(ValidationError):
        merge_rule(rule, AlertRulePatch(channel="telegram"))  # sem target: inválido
