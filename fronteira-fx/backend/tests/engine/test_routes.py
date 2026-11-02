from decimal import Decimal

import pytest

from fronteira_fx.engine.positions import Position
from fronteira_fx.engine.routes import Fee, RouteError, StepSpec, simulate_route

D = Decimal
BRL_PIX = Position("BRL", institution="banco", location="digital", modality="transfer")
PYG_UENO = Position("PYG", institution="ueno", location="digital", modality="account")
BRL_CDE = Position("BRL", institution="chaco", location="CDE", modality="cash")
PYG_CDE = Position("PYG", institution="chaco", location="CDE", modality="cash")


def cycle(fee_brl: Decimal | None = D("10"), rate_out=D("1380"), rate_back=D("1378")):
    fees = (Fee("tarifa WU", fee_brl, "BRL"),)
    return [
        StepSpec("BRL -> PYG via WU", BRL_PIX, PYG_UENO, rate=rate_out, fees=fees, confidence="quoted"),
        StepSpec("PYG -> BRL em CDE", PYG_CDE, BRL_CDE, rate=D(1) / rate_back, confidence="estimated"),
    ]


def test_steps_chain_and_fee_applied_exactly_once():
    res = simulate_route(cycle(), D("5000"))
    assert res.steps[0].amount_in == D("5000")
    expected_pyg = (D("5000") - D("10")) * D("1380")
    assert res.steps[0].amount_out == expected_pyg
    assert res.steps[1].amount_in == expected_pyg
    assert res.net_credit == expected_pyg * (D(1) / D("1378"))
    # fee counted once: total fees valued == 10 BRL, and final + fee*rate_ratio reconstructs the gross path
    assert res.total_fees_valued == D("10") * D("1380") * (D(1) / D("1378"))
    gross_without_fee = D("5000") * D("1380") * (D(1) / D("1378"))
    assert abs(res.net_credit - (gross_without_fee - res.total_fees_valued)) < D("1e-20")


def test_effective_rate_profit_and_roi_definitions():
    res = simulate_route(cycle(fee_brl=D("0")), D("5000"))
    assert res.effective_rate == res.net_credit / res.total_debit
    assert res.cycle_profit == res.final_available - res.total_capital_allocated
    assert res.roi == res.cycle_profit / res.total_capital_allocated
    assert res.confidence == "estimated"  # weakest step wins
    assert res.pending_costs == ()


def test_fee_in_output_currency_and_third_currency():
    steps = [
        StepSpec(
            "BRL -> PYG",
            BRL_PIX,
            PYG_UENO,
            rate=D("1000"),
            fees=(Fee("tarifa destino", D("5000"), "PYG"), Fee("tarifa USD", D("1"), "USD", rate_to_output=D("7000"))),
        ),
    ]
    res = simulate_route(steps, D("100"), valuation_currency="PYG", valuation_rates={"BRL": D("1000")})
    assert res.net_credit == D("100") * D("1000") - D("5000") - D("7000")
    assert res.confidence == "quoted"


def test_unknown_fee_marks_incomplete_and_pending():
    steps = [
        StepSpec("BRL -> PYG", BRL_PIX, PYG_UENO, rate=D("1000"), fees=(Fee("IOF", None, "BRL"),)),
        StepSpec("PYG -> BRL", PYG_CDE, BRL_CDE, rate=D("0.001")),
    ]
    res = simulate_route(steps, D("5000"))
    assert res.confidence == "incomplete"
    assert any("IOF" in p for p in res.pending_costs)
    # third-currency fee without a rate is also pending
    steps2 = [StepSpec("BRL -> PYG", BRL_PIX, PYG_UENO, rate=D("1000"), fees=(Fee("tarifa", D("2"), "USD"),))]
    res2 = simulate_route(steps2, D("5000"), valuation_currency=None)
    assert res2.confidence == "incomplete"
    assert any("USD" in p for p in res2.pending_costs)


def test_micro_gain_is_preserved_exactly():
    # +0.37 BRL on 5000: rate_back chosen so the gain is tiny but strictly positive
    capital = D("5000")
    steps = [
        StepSpec("out", BRL_PIX, PYG_UENO, rate=D("1380")),
        StepSpec("back", PYG_CDE, BRL_CDE, rate=D("5000.37") / (capital * D("1380"))),
    ]
    res = simulate_route(steps, capital)
    assert res.cycle_profit > 0
    assert res.cycle_profit.quantize(D("0.01")) == D("0.37")


def test_missing_valuation_rate_is_pending():
    steps = [StepSpec("BRL -> PYG", BRL_PIX, PYG_UENO, rate=D("1000"))]
    res = simulate_route(steps, D("100"))
    assert res.final_available is None
    assert res.roi is None
    assert res.confidence == "incomplete"
    res2 = simulate_route(steps, D("100"), valuation_rates={"PYG": D("0.001")})
    assert res2.final_available == D("100")
    assert res2.cycle_profit == 0


def test_determinism_and_amount_sensitivity():
    a = simulate_route(cycle(), D("5000"))
    b = simulate_route(cycle(), D("5000"))
    assert a == b
    assert a.to_dict() == b.to_dict()
    c = simulate_route(cycle(), D("10000"))
    assert c.net_credit != a.net_credit
    assert c.roi != a.roi  # fixed fee => roi depends on the amount


def test_route_errors():
    with pytest.raises(RouteError):
        simulate_route([StepSpec("x", BRL_PIX, PYG_UENO)], D("100"))  # missing rate across currencies
    with pytest.raises(RouteError):
        simulate_route(cycle(), D("0"))
    with pytest.raises(RouteError):
        simulate_route(
            [StepSpec("x", BRL_PIX, PYG_UENO, rate=D("1")), StepSpec("y", BRL_PIX, PYG_UENO, rate=D("1"))], D("1")
        )
    same = simulate_route([StepSpec("transfer", BRL_PIX, BRL_CDE)], D("100"))
    assert same.net_credit == D("100") and same.steps[0].rate == 1
