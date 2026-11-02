"""ueno card "Pagar uma compra" scenarios.

Scenarios
---------
1. BRL -> Western Union -> ueno balance -> card purchase
2. ueno balance -> PYG/USD conversion -> card purchase
3. ueno balance -> credit invoice payment

Debit, credit and virtual cards are kept separate. Every result records the purchase currency, the
debited account/currency, the conversion applied, fees, benefits and the final posted amount; credit
purchases also compute the invoice payment. Until the debited currency *and* the charges are validated
against real statements the confidence is `incomplete` - a USD balance is never assumed automatically.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import ONE, ZERO, fmt
from .routes import Confidence, Fee, RouteError, RouteResult, StepSpec, combine_confidence, simulate_route

CardType = Literal["debit", "credit", "virtual"]
CARD_MODALITY: dict[str, str] = {"debit": "card_debit", "credit": "card_credit", "virtual": "card_virtual"}


@dataclass(frozen=True, slots=True)
class CardPurchase:
    amount: Decimal  # purchase amount, in `currency`
    currency: str
    card_type: CardType
    card_label: str = "ueno cartão"
    debited_account: str | None = None  # label/id of the account the card charges
    debited_currency: str | None = None  # None => not validated yet (never assume USD)
    conversion_rate: Decimal | None = None  # debited units per 1 purchase unit, when currencies differ
    fees: tuple[Fee, ...] = ()  # spread, IOF, international fee...
    benefits: tuple[Fee, ...] = ()  # cashback / promo credits
    charges_validated: bool = False  # confirmed on a real statement / evidence
    confidence: Confidence = "estimated"


@dataclass(frozen=True, slots=True)
class CardPurchaseResult:
    card_type: CardType
    card_label: str
    purchase_amount: Decimal
    purchase_currency: str
    debited_account: str | None
    debited_currency: str | None
    conversion_rate: Decimal | None
    converted_amount: Decimal | None  # purchase amount in debited currency, before fees
    fees: tuple[Fee, ...]
    fees_total: Decimal | None  # known fees in debited currency
    benefits: tuple[Fee, ...]
    benefits_total: Decimal | None
    final_posted_amount: Decimal | None  # what actually hits the account / invoice
    invoice_payment: Decimal | None  # credit only: amount to pay on the invoice
    confidence: Confidence
    pending_costs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_type": self.card_type,
            "card_label": self.card_label,
            "modality": CARD_MODALITY[self.card_type],
            "purchase_amount": fmt(self.purchase_amount),
            "purchase_currency": self.purchase_currency,
            "debited_account": self.debited_account,
            "debited_currency": self.debited_currency,
            "conversion_rate": fmt(self.conversion_rate),
            "converted_amount": fmt(self.converted_amount),
            "fees": [f.to_dict() for f in self.fees],
            "fees_total": fmt(self.fees_total),
            "benefits": [b.to_dict() for b in self.benefits],
            "benefits_total": fmt(self.benefits_total),
            "final_posted_amount": fmt(self.final_posted_amount),
            "invoice_payment": fmt(self.invoice_payment),
            "confidence": self.confidence,
            "pending_costs": list(self.pending_costs),
        }


def _sum_in_currency(
    items: Sequence[Fee], target: str, purchase_ccy: str, rate: Decimal | None, pending: list[str], what: str
) -> Decimal | None:
    total: Decimal | None = ZERO
    for it in items:
        if it.amount is None:
            pending.append(f"{what} {it.label} ({it.currency}): valor desconhecido")
            total = None
            continue
        if it.currency == target:
            value = it.amount
        elif it.currency == purchase_ccy and rate is not None:
            value = it.amount * rate
        elif it.rate_to_output is not None:
            value = it.amount * it.rate_to_output
        else:
            pending.append(f"{what} {it.label} ({it.currency}): sem taxa de conversão para {target}")
            total = None
            continue
        if total is not None:
            total += value
    return total


def simulate_card_purchase(p: CardPurchase) -> CardPurchaseResult:
    pending: list[str] = []
    converted: Decimal | None = None
    rate: Decimal | None = None
    fees_total: Decimal | None = None
    benefits_total: Decimal | None = None
    final: Decimal | None = None

    if p.debited_currency is None:
        pending.append("moeda da conta debitada não validada (não assumir saldo USD automaticamente)")
    else:
        if p.debited_currency == p.currency:
            rate = ONE
        elif p.conversion_rate is not None and p.conversion_rate > 0:
            rate = p.conversion_rate
        else:
            pending.append(f"taxa de conversão {p.currency}->{p.debited_currency} do cartão desconhecida")
        if rate is not None:
            converted = p.amount * rate
        fees_total = _sum_in_currency(p.fees, p.debited_currency, p.currency, rate, pending, "tarifa")
        benefits_total = _sum_in_currency(p.benefits, p.debited_currency, p.currency, rate, pending, "benefício")
        if converted is not None and fees_total is not None and benefits_total is not None:
            final = converted + fees_total - benefits_total

    if not p.charges_validated:
        pending.append("encargos do cartão (spread/IOF/tarifa internacional) não validados em extrato")

    confidence = combine_confidence(p.confidence, "incomplete" if pending else "quoted")
    return CardPurchaseResult(
        card_type=p.card_type,
        card_label=p.card_label,
        purchase_amount=p.amount,
        purchase_currency=p.currency,
        debited_account=p.debited_account,
        debited_currency=p.debited_currency,
        conversion_rate=rate,
        converted_amount=converted,
        fees=p.fees,
        fees_total=fees_total,
        benefits=p.benefits,
        benefits_total=benefits_total,
        final_posted_amount=final,
        invoice_payment=final if p.card_type == "credit" else None,
        confidence=confidence,
        pending_costs=tuple(pending),
    )


@dataclass(frozen=True, slots=True)
class CardScenarioResult:
    name: str
    funding: RouteResult | None  # steps that build the balance the card uses
    purchase: CardPurchaseResult
    settlement: RouteResult | None  # credit: balance -> invoice payment
    balance_before: Decimal | None  # in the debited currency
    balance_after: Decimal | None
    total_cost_valued: Decimal | None  # cost of the purchase in valuation currency
    valuation_currency: str
    confidence: Confidence
    pending_costs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "funding": self.funding.to_dict() if self.funding else None,
            "purchase": self.purchase.to_dict(),
            "settlement": self.settlement.to_dict() if self.settlement else None,
            "balance_before": fmt(self.balance_before),
            "balance_after": fmt(self.balance_after),
            "total_cost_valued": fmt(self.total_cost_valued),
            "valuation_currency": self.valuation_currency,
            "confidence": self.confidence,
            "pending_costs": list(self.pending_costs),
        }


def _cost_valued(
    amount: Decimal | None,
    currency: str | None,
    funding: RouteResult | None,
    valuation_currency: str,
    rates: Mapping[str, Decimal],
    pending: list[str],
) -> Decimal | None:
    if amount is None or currency is None:
        return None
    if currency == valuation_currency:
        return amount
    if funding is not None and funding.final_currency == currency and funding.effective_rate:
        return amount / funding.effective_rate  # what it cost, at the rate the balance was built
    rate = rates.get(currency)
    if rate is not None:
        return amount * rate
    pending.append(f"cotação {currency}->{valuation_currency} para valorar o custo da compra")
    return None


def simulate_card_scenario(
    name: str,
    purchase: CardPurchase,
    *,
    funding_steps: Sequence[StepSpec] = (),
    capital: Decimal | None = None,
    balance: Decimal | None = None,
    settlement_step: StepSpec | None = None,
    valuation_currency: str = "BRL",
    valuation_rates: Mapping[str, Decimal] | None = None,
) -> CardScenarioResult:
    """Generic scenario: optional funding route, the card purchase, optional invoice settlement.

    `capital` feeds `funding_steps`; `balance` is an existing balance in the debited currency when
    there is no funding route. For credit cards `settlement_step` converts balance -> invoice currency.
    """
    rates = dict(valuation_rates or {})
    pending: list[str] = []
    funding: RouteResult | None = None
    balance_before: Decimal | None = balance
    balance_ccy: str | None = purchase.debited_currency

    if funding_steps:
        if capital is None:
            raise RouteError("capital is required when funding_steps are given")
        funding = simulate_route(funding_steps, capital, valuation_currency=None)
        balance_before = funding.net_credit
        balance_ccy = funding.final_currency
        pending.extend(funding.pending_costs)

    result = simulate_card_purchase(purchase)
    pending.extend(result.pending_costs)
    if purchase.debited_currency is not None and balance_ccy is not None and purchase.debited_currency != balance_ccy:
        pending.append(
            f"saldo em {balance_ccy} mas o cartão debita {purchase.debited_currency}: conversão não modelada"
        )

    settlement: RouteResult | None = None
    charge = result.final_posted_amount
    if purchase.card_type == "credit" and settlement_step is not None and result.invoice_payment is not None:
        # how much balance must leave to settle the invoice: invert the single settlement step
        fees_in = sum(
            (
                f.amount
                for f in settlement_step.fees
                if f.amount is not None and f.currency == settlement_step.from_position.currency
            ),
            ZERO,
        )
        fees_out = sum(
            (
                f.amount
                for f in settlement_step.fees
                if f.amount is not None and f.currency == settlement_step.to_position.currency
            ),
            ZERO,
        )
        for f in settlement_step.fees:
            if f.amount is None:
                pending.append(f"{f.label} ({f.currency}): valor desconhecido no pagamento da fatura")
        rate = settlement_step.rate or (
            ONE if settlement_step.from_position.currency == settlement_step.to_position.currency else None
        )
        if rate is None:
            raise RouteError("settlement step needs a rate")
        needed = (result.invoice_payment + fees_out) / rate + fees_in
        settlement = simulate_route([settlement_step], needed, valuation_currency=None)
        charge = needed
        balance_ccy = settlement_step.from_position.currency if balance_ccy is None else balance_ccy

    balance_after = balance_before - charge if balance_before is not None and charge is not None else None
    cost_ccy = balance_ccy if settlement is not None else purchase.debited_currency
    total_cost = _cost_valued(charge, cost_ccy, funding, valuation_currency, rates, pending)

    confidence = combine_confidence(
        result.confidence,
        funding.confidence if funding else "quoted",
        settlement.confidence if settlement else "quoted",
        "incomplete" if pending else "quoted",
    )
    return CardScenarioResult(
        name=name,
        funding=funding,
        purchase=result,
        settlement=settlement,
        balance_before=balance_before,
        balance_after=balance_after,
        total_cost_valued=total_cost,
        valuation_currency=valuation_currency,
        confidence=confidence,
        pending_costs=tuple(dict.fromkeys(pending)),
    )


def scenario_wu_to_ueno_then_pay(
    capital_brl: Decimal, wu_step: StepSpec, purchase: CardPurchase, **kw: Any
) -> CardScenarioResult:
    """BRL -> Western Union -> ueno balance -> card purchase."""
    return simulate_card_scenario(
        "BRL → WU → saldo ueno → compra no cartão", purchase, funding_steps=[wu_step], capital=capital_brl, **kw
    )


def scenario_convert_balance_then_pay(
    balance: Decimal, conversion_step: StepSpec, purchase: CardPurchase, **kw: Any
) -> CardScenarioResult:
    """ueno balance -> PYG/USD conversion -> card purchase."""
    return simulate_card_scenario(
        "saldo ueno → conversão → compra no cartão", purchase, funding_steps=[conversion_step], capital=balance, **kw
    )


def scenario_credit_invoice_payment(
    balance: Decimal, purchase: CardPurchase, settlement_step: StepSpec | None = None, **kw: Any
) -> CardScenarioResult:
    """ueno balance -> credit card invoice payment."""
    if purchase.card_type != "credit":
        raise RouteError("invoice payment scenario requires a credit card purchase")
    return simulate_card_scenario(
        "saldo ueno → pagamento da fatura do cartão de crédito",
        purchase,
        balance=balance,
        settlement_step=settlement_step,
        **kw,
    )
