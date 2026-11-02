from __future__ import annotations

from decimal import Decimal

import pytest

from fronteira_fx.notify import messages as m

D = Decimal


@pytest.mark.parametrize(
    ("value", "currency", "signed", "expected"),
    [
        (D("41.2"), "BRL", True, "+R$ 41,20"),
        (D("5000"), "BRL", False, "R$ 5.000,00"),
        (D("-3"), "BRL", True, "-R$ 3,00"),
        (D("0"), "BRL", True, "R$ 0,00"),
        (D("41200"), "PYG", False, "Gs 41.200"),
        (D("1234567.891"), "USD", False, "US$ 1.234.567,89"),
        (D("0.005"), "BRL", False, "R$ 0,01"),  # meio arredonda para cima
    ],
)
def test_fmt_money(value, currency, signed, expected):
    assert m.fmt_money(value, currency, signed=signed) == expected


@pytest.mark.parametrize(
    ("ratio", "signed", "expected"),
    [
        (D("0.001648"), False, "0,165 %"),
        (D("0.00940"), True, "+0,940 %"),
        (D("-0.00006"), False, "-0,006 %"),
        (D("0"), True, "0,000 %"),
    ],
)
def test_fmt_pct_turns_fraction_into_percent(ratio, signed, expected):
    assert m.fmt_pct(ratio, signed=signed) == expected


def test_fmt_rate_keeps_pyg_integer_and_four_places_elsewhere():
    assert m.fmt_rate(D("7450"), "PYG") == "7.450"
    assert m.fmt_rate(D("5.41234"), "BRL") == "5,4123"


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (D(0), "0 min"),
        (D(45), "45 min"),
        (D(300), "5,0 h"),
        (D(4320), "3,0 d"),
        (D(1500), "1,0 d"),
    ],
)
def test_fmt_duration(minutes, expected):
    assert m.fmt_duration(minutes) == expected


def test_cycle_text_matches_contract_example_and_incomplete_suffix():
    text = m.cycle_text(
        path=["BRL@brbank", "PYG@ueno", "USD@ueno", "BRL@brbank"],
        gain=D("41.2"),
        roi=D("0.001648"),
        minutes=D(4320),
        confidence="estimated",
        currency="BRL",
    )
    assert text == "Ciclo BRL@brbank → PYG@ueno → USD@ueno → BRL@brbank: +R$ 41,20 (0,165 %) em 3,0 d"
    incomplete = m.cycle_text(
        path=["BRL@a", "BRL@a"],
        gain=D("-2"),
        roi=D("-0.0004"),
        minutes=D(60),
        confidence="incomplete",
        currency="BRL",
    )
    assert incomplete == "Ciclo BRL@a → BRL@a: -R$ 2,00 (-0,040 %) em 1,0 h — incompleto (há custo pendente)"


def test_quote_move_text_names_city_or_digital():
    city = m.quote_move_text(
        base="USD", quote="PYG", city="CDE", source_id="chaco",
        previous=D("7450"), current=D("7520"), ratio=D("70") / D("7450"),
    )
    assert city == "USD/PYG em CDE (chaco): 7.450 → 7.520 PYG por 1 USD (+0,940 %)"
    digital = m.quote_move_text(
        base="USD", quote="PYG", city=None, source_id="ueno",
        previous=D("7450"), current=D("7400"), ratio=D("-50") / D("7450"),
    )
    assert digital.startswith("USD/PYG digital (ueno): 7.450 → 7.400 PYG por 1 USD (-0,671 %)")


def test_opportunity_text_with_and_without_numbers():
    full = m.opportunity_text(title="Ciclo X", net_gain=D("42.10"), roi=D("0.00842"), capital=D("5000"))
    assert full == (
        "Nova oportunidade no ranking principal: Ciclo X — ganho líquido +R$ 42,10, ROI +0,842 %, capital R$ 5.000,00"
    )
    assert m.opportunity_text(title="Ciclo X", net_gain=None, roi=None, capital=None) == (
        "Nova oportunidade no ranking principal: Ciclo X"
    )


def test_source_down_text_clips_long_detail_and_flattens_newlines():
    detail = "linha 1\nlinha 2 " + "x" * 400
    text = m.source_down_text(label="Ueno (ueno)", health="error", detail=detail)
    assert text.startswith("Fonte Ueno (ueno) com erro. Detalhe: linha 1 linha 2 ")
    assert "\n" not in text
    assert len(text) < 260


def test_source_down_text_default_detail_and_unknown_state():
    assert m.source_down_text(label="X", health="blocked", detail=None) == "Fonte X bloqueada. Detalhe: sem detalhes"
    assert m.source_down_text(label="X", health="stale", detail="ok").startswith("Fonte X em estado stale")


def test_delivery_check_text():
    text = m.delivery_check_text(rule_name="ciclo > 0,2 %", channel="telegram")
    assert text == "Teste do alerta «ciclo > 0,2 %» pelo canal telegram: a entrega está funcionando."
