from decimal import Decimal

import pytest

from fronteira_fx.engine.cards import (
    CardPurchase,
    scenario_convert_balance_then_pay,
    scenario_credit_invoice_payment,
    scenario_wu_to_ueno_then_pay,
    simulate_card_purchase,
)
from fronteira_fx.engine.positions import Position
from fronteira_fx.engine.routes import Fee, RouteError, StepSpec

D = Decimal
BRL_PIX = Position("BRL", institution="banco", modality="transfer")
PYG_UENO = Position("PYG", institution="ueno", modality="account")
USD_UENO = Position("USD", institution="ueno", modality="account")
WU = StepSpec("Pix BRL -> WU -> ueno PYG", BRL_PIX, PYG_UENO, rate=D("1380"), fees=(Fee("tarifa", D("0"), "BRL"),))


def test_debited_currency_not_validated_is_incomplete_and_never_assumes_usd():
    p = CardPurchase(amount=D("100"), currency="USD", card_type="debit", debited_currency=None, charges_validated=True)
    r = simulate_card_purchase(p)
    assert r.confidence == "incomplete"
    assert r.final_posted_amount is None and r.debited_currency is None
    assert any("não assumir saldo USD" in x for x in r.pending_costs)


def test_charges_not_validated_is_incomplete_even_with_all_numbers():
    p = CardPurchase(
        amount=D("100"),
        currency="USD",
        card_type="debit",
        debited_account="ueno PYG",
        debited_currency="PYG",
        conversion_rate=D("7400"),
        fees=(Fee("spread", D("3"), "USD"),),
        charges_validated=False,
    )
    r = simulate_card_purchase(p)
    assert r.final_posted_amount == D("100") * D("7400") + D("3") * D("7400")
    assert r.confidence == "incomplete"
    assert any("não validados" in x for x in r.pending_costs)


def test_validated_debit_purchase_records_everything():
    p = CardPurchase(
        amount=D("250000"),
        currency="PYG",
        card_type="debit",
        debited_account="ueno PYG",
        debited_currency="PYG",
        fees=(Fee("tarifa", D("1500"), "PYG"),),
        benefits=(Fee("cashback 1%", D("2500"), "PYG"),),
        charges_validated=True,
        confidence="quoted",
    )
    r = simulate_card_purchase(p)
    assert r.confidence == "quoted"
    assert r.conversion_rate == 1 and r.converted_amount == D("250000")
    assert r.fees_total == D("1500") and r.benefits_total == D("2500")
    assert r.final_posted_amount == D("249000")
    assert r.invoice_payment is None  # debit: no invoice
    d = r.to_dict()
    assert d["modality"] == "card_debit" and d["purchase_currency"] == "PYG" and d["debited_account"] == "ueno PYG"


def test_credit_purchase_computes_invoice_payment_and_virtual_is_separate():
    credit = CardPurchase(
        amount=D("100"),
        currency="USD",
        card_type="credit",
        debited_account="ueno crédito PYG",
        debited_currency="PYG",
        conversion_rate=D("7400"),
        charges_validated=True,
        confidence="quoted",
    )
    r = simulate_card_purchase(credit)
    assert r.invoice_payment == D("740000") and r.final_posted_amount == D("740000")
    virtual = simulate_card_purchase(
        CardPurchase(
            amount=D("100"),
            currency="USD",
            card_type="virtual",
            debited_currency="USD",
            charges_validated=True,
            confidence="quoted",
        )
    )
    assert virtual.to_dict()["modality"] == "card_virtual" and virtual.invoice_payment is None
    assert virtual.final_posted_amount == D("100")


def test_scenario_wu_to_ueno_then_pay():
    purchase = CardPurchase(
        amount=D("1000000"),
        currency="PYG",
        card_type="debit",
        debited_account="ueno PYG",
        debited_currency="PYG",
        charges_validated=True,
        confidence="quoted",
    )
    s = scenario_wu_to_ueno_then_pay(D("5000"), WU, purchase)
    assert s.funding is not None and s.funding.net_credit == D("5000") * D("1380")
    assert s.balance_before == D("6900000") and s.balance_after == D("5900000")
    assert s.total_cost_valued == D("1000000") / D("1380")  # BRL cost at the funding rate
    assert s.confidence == "quoted"
    # mismatch: card debits USD but the balance built is PYG => flagged
    bad = CardPurchase(
        amount=D("100"), currency="USD", card_type="debit", debited_currency="USD", charges_validated=True
    )
    s2 = scenario_wu_to_ueno_then_pay(D("5000"), WU, bad)
    assert s2.confidence == "incomplete" and any("conversão não modelada" in p for p in s2.pending_costs)


def test_scenario_convert_balance_then_pay():
    conv = StepSpec("ueno PYG -> USD", PYG_UENO, USD_UENO, rate=D(1) / D("7395"), confidence="quoted")
    purchase = CardPurchase(
        amount=D("100"),
        currency="USD",
        card_type="debit",
        debited_account="ueno USD",
        debited_currency="USD",
        charges_validated=True,
        confidence="quoted",
    )
    s = scenario_convert_balance_then_pay(D("1000000"), conv, purchase, valuation_rates={"PYG": D(1) / D("1380")})
    assert s.funding.final_currency == "USD"
    assert s.balance_after == s.balance_before - D("100")
    assert s.confidence == "quoted"


def test_scenario_credit_invoice_payment():
    purchase = CardPurchase(
        amount=D("100"),
        currency="USD",
        card_type="credit",
        debited_account="ueno crédito PYG",
        debited_currency="PYG",
        conversion_rate=D("7400"),
        charges_validated=True,
        confidence="quoted",
    )
    s = scenario_credit_invoice_payment(D("2500000"), purchase, valuation_rates={"PYG": D(1) / D("1380")})
    assert s.purchase.invoice_payment == D("740000")
    assert s.balance_after == D("2500000") - D("740000")
    assert s.total_cost_valued == D("740000") / D("1380")
    # paying a PYG invoice from a USD balance needs a settlement step
    pay = StepSpec("USD -> PYG para fatura", USD_UENO, PYG_UENO, rate=D("7270"), fees=(Fee("tarifa", D("1"), "USD"),))
    s2 = scenario_credit_invoice_payment(D("500"), purchase, settlement_step=pay, valuation_rates={"USD": D("5.4")})
    needed = D("740000") / D("7270") + D("1")
    assert s2.settlement is not None and s2.balance_after == D("500") - needed
    with pytest.raises(RouteError):
        scenario_credit_invoice_payment(D("1"), CardPurchase(amount=D("1"), currency="USD", card_type="debit"))
