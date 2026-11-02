"""Route simulation: each step consumes the previous step's output.

Conventions
-----------
* `StepSpec.rate` is *to.currency per 1 from.currency*. Same-currency steps default to 1.
* Fees are applied exactly once, at the step that charges them:
  - fee in the step's input currency  -> deducted before conversion
  - fee in the step's output currency -> deducted after conversion
  - fee in a third currency           -> converted with `Fee.rate_to_output` when given,
                                         otherwise it is an *unknown cost*
  - `Fee.amount is None`              -> unknown cost
* Any unknown cost makes the route `incomplete` and is listed in `pending_costs`.
* `effective_rate = net_credit / total_debit`, `cycle_profit = final_available - capital`,
  `roi = net_profit / total_capital_allocated` (valuation currency, BRL by default).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import ONE, ZERO, fmt
from .positions import Position

Confidence = Literal["quoted", "estimated", "incomplete"]
_CONF_ORDER = {"quoted": 0, "estimated": 1, "incomplete": 2}


def combine_confidence(*levels: str) -> Confidence:
    worst: Confidence = "quoted"
    for lv in levels:
        if _CONF_ORDER.get(lv, 2) > _CONF_ORDER[worst]:
            worst = lv if lv in _CONF_ORDER else "incomplete"  # type: ignore[assignment]
    return worst


class RouteError(ValueError):
    """Raised when a route cannot be simulated at all (e.g. missing rate)."""


@dataclass(frozen=True, slots=True)
class Fee:
    label: str
    amount: Decimal | None  # None => unknown
    currency: str
    rate_to_output: Decimal | None = None  # output units per 1 fee unit (third-currency fees)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "amount": fmt(self.amount) if self.amount is not None else None,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class StepSpec:
    description: str
    from_position: Position
    to_position: Position
    rate: Decimal | None = None
    rate_note: str = ""
    fees: tuple[Fee, ...] = ()
    duration: str = ""
    promo: str | None = None
    confidence: Confidence = "quoted"
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class StepResult:
    n: int
    description: str
    from_position: Position
    to_position: Position
    rate: Decimal | None
    rate_note: str
    amount_in: Decimal
    amount_out: Decimal
    fees: tuple[Fee, ...]
    fees_in_output: Decimal  # all known fees of this step, expressed in the output currency
    duration: str
    promo: str | None
    confidence: Confidence
    evidence_id: str | None
    pending_costs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "description": self.description,
            "from": self.from_position.to_dict(self.amount_in),
            "to": self.to_position.to_dict(self.amount_out),
            "rate": fmt(self.rate),
            "rate_note": self.rate_note,
            "amount_in": fmt(self.amount_in),
            "amount_out": fmt(self.amount_out),
            "fees": [f.to_dict() for f in self.fees],
            "duration": self.duration,
            "promo": self.promo,
            "confidence": self.confidence,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class RouteResult:
    steps: tuple[StepResult, ...]
    start_currency: str
    final_currency: str
    valuation_currency: str
    total_debit: Decimal  # capital that left the first position (start currency)
    net_credit: Decimal  # what arrives in the final position (final currency)
    total_capital_allocated: Decimal | None  # capital valued in valuation currency
    final_available: Decimal | None  # net_credit valued in valuation currency
    effective_rate: Decimal | None  # net_credit / total_debit
    cycle_profit: Decimal | None  # final_available - total_capital_allocated
    roi: Decimal | None  # net_profit / total_capital_allocated
    total_fees_valued: Decimal | None  # all known fees in valuation currency (informational)
    confidence: Confidence
    pending_costs: tuple[str, ...]

    @property
    def net_profit(self) -> Decimal | None:
        return self.cycle_profit

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "start_currency": self.start_currency,
            "final_currency": self.final_currency,
            "valuation_currency": self.valuation_currency,
            "total_debit": fmt(self.total_debit),
            "net_credit": fmt(self.net_credit),
            "total_capital_allocated": fmt(self.total_capital_allocated),
            "final_available": fmt(self.final_available),
            "effective_rate": fmt(self.effective_rate),
            "cycle_profit": fmt(self.cycle_profit),
            "roi": fmt(self.roi),
            "total_fees_valued": fmt(self.total_fees_valued),
            "confidence": self.confidence,
            "pending_costs": list(self.pending_costs),
        }


def _value(amount: Decimal, currency: str, valuation: str, rates: Mapping[str, Decimal]) -> Decimal | None:
    if currency == valuation:
        return amount
    rate = rates.get(currency)
    if rate is None:
        return None
    return amount * rate


def simulate_step(spec: StepSpec, amount_in: Decimal, n: int) -> StepResult:
    from_ccy = spec.from_position.currency
    to_ccy = spec.to_position.currency
    rate = spec.rate
    if rate is None:
        if from_ccy == to_ccy:
            rate = ONE
        else:
            raise RouteError(f"step {n}: rate {from_ccy}->{to_ccy} is required")
    if rate <= 0:
        raise RouteError(f"step {n}: rate must be positive")

    pending: list[str] = []
    fees_in = ZERO
    fees_out = ZERO
    for fee in spec.fees:
        if fee.amount is None:
            pending.append(f"{fee.label} ({fee.currency}): valor desconhecido")
            continue
        if fee.currency == from_ccy:
            fees_in += fee.amount
        elif fee.currency == to_ccy:
            fees_out += fee.amount
        elif fee.rate_to_output is not None:
            fees_out += fee.amount * fee.rate_to_output
        else:
            pending.append(f"{fee.label} ({fee.currency}): sem taxa de conversão para {to_ccy}")

    net_in = amount_in - fees_in
    amount_out = net_in * rate - fees_out
    confidence = combine_confidence(spec.confidence, "incomplete" if pending else "quoted")
    return StepResult(
        n=n,
        description=spec.description,
        from_position=spec.from_position,
        to_position=spec.to_position,
        rate=rate,
        rate_note=spec.rate_note or f"{to_ccy} por 1 {from_ccy}",
        amount_in=amount_in,
        amount_out=amount_out,
        fees=spec.fees,
        fees_in_output=fees_in * rate + fees_out,
        duration=spec.duration,
        promo=spec.promo,
        confidence=confidence,
        evidence_id=spec.evidence_id,
        pending_costs=tuple(pending),
    )


def simulate_route(
    steps: Sequence[StepSpec],
    capital: Decimal,
    *,
    valuation_currency: str | None = "BRL",
    valuation_rates: Mapping[str, Decimal] | None = None,
) -> RouteResult:
    """Simulate `steps` starting with `capital` in the first step's input currency.

    `valuation_rates` maps currency -> valuation units per 1 unit (used when the start or
    final currency differs from `valuation_currency`). `valuation_currency=None` skips valuation
    (profit/roi are None and no valuation cost is marked pending).
    """
    if not steps:
        raise RouteError("route needs at least one step")
    if capital <= 0:
        raise RouteError("capital must be positive")
    rates = dict(valuation_rates or {})

    results: list[StepResult] = []
    amount = capital
    for i, spec in enumerate(steps, start=1):
        if i > 1 and spec.from_position.currency != results[-1].to_position.currency:
            raise RouteError(
                f"step {i}: input currency {spec.from_position.currency} != previous output "
                f"{results[-1].to_position.currency}"
            )
        res = simulate_step(spec, amount, i)
        results.append(res)
        amount = res.amount_out

    start_ccy = steps[0].from_position.currency
    final_ccy = steps[-1].to_position.currency
    pending = [p for r in results for p in r.pending_costs]

    if valuation_currency is None:
        capital_valued = final_valued = None
    else:
        capital_valued = _value(capital, start_ccy, valuation_currency, rates)
        final_valued = _value(amount, final_ccy, valuation_currency, rates)
        if capital_valued is None:
            pending.append(f"cotação {start_ccy}->{valuation_currency} para valorar o capital")
        if final_valued is None:
            pending.append(f"cotação {final_ccy}->{valuation_currency} para valorar o resultado")

    effective_rate = amount / capital if capital else None
    profit = roi = None
    if capital_valued is not None and final_valued is not None:
        profit = final_valued - capital_valued
        roi = profit / capital_valued if capital_valued else None

    # every fee, carried forward through the downstream rates => its exact impact on the final amount
    fees_final = ZERO
    carry = ONE
    for r in reversed(results):
        fees_final += r.fees_in_output * carry
        carry *= r.rate if r.rate is not None else ONE
    fees_valued = _value(fees_final, final_ccy, valuation_currency, rates) if valuation_currency else None

    confidence = combine_confidence(*(r.confidence for r in results), "incomplete" if pending else "quoted")
    return RouteResult(
        steps=tuple(results),
        start_currency=start_ccy,
        final_currency=final_ccy,
        valuation_currency=valuation_currency or start_ccy,
        total_debit=capital,
        net_credit=amount,
        total_capital_allocated=capital_valued,
        final_available=final_valued,
        effective_rate=effective_rate,
        cycle_profit=profit,
        roi=roi,
        total_fees_valued=fees_valued,
        confidence=confidence,
        pending_costs=tuple(pending),
    )
