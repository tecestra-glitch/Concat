"""Adaptive amount search: coarse grid, then bisect where the winner or the roi sign changes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from ..decimal_utils import fmt, sign

DEFAULT_AMOUNTS: tuple[Decimal, ...] = (Decimal("5000"), Decimal("10000"), Decimal("25000"), Decimal("50000"))
MIN_AMOUNT = Decimal("5000")
MAX_AMOUNT = Decimal("50000")


@dataclass(frozen=True, slots=True)
class Evaluation:
    amount: Decimal
    winner: str | None  # id of the best main-ranking opportunity, None when nothing wins
    roi: Decimal | None  # roi of the winner (sign matters)
    payload: Any = None  # whatever the evaluator wants to keep (e.g. ranked list)

    @property
    def roi_sign(self) -> str:
        return sign(self.roi)


@dataclass(frozen=True, slots=True)
class Boundary:
    low: Decimal
    high: Decimal
    low_winner: str | None
    high_winner: str | None
    low_roi_sign: str
    high_roi_sign: str
    reason: str
    refined: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "low": fmt(self.low),
            "high": fmt(self.high),
            "low_winner": self.low_winner,
            "high_winner": self.high_winner,
            "low_roi_sign": self.low_roi_sign,
            "high_roi_sign": self.high_roi_sign,
            "reason": self.reason,
            "refined": self.refined,
        }


@dataclass(slots=True)
class SearchResult:
    amounts_tested: list[Decimal]
    boundaries: list[Boundary]
    evaluations: dict[Decimal, Evaluation] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "amounts_tested": [fmt(a) for a in self.amounts_tested],
            "boundaries": [b.to_dict() for b in self.boundaries],
        }


def _differs(a: Evaluation, b: Evaluation) -> str | None:
    if a.winner != b.winner:
        return "winner_changes"
    if a.roi_sign != b.roi_sign:
        return "roi_sign_changes"
    return None


def adaptive_amount_search(
    evaluate: Callable[[Decimal], Evaluation],
    *,
    amounts: Iterable[Decimal] = DEFAULT_AMOUNTS,
    supports: Callable[[Decimal], bool] = lambda _a: True,
    max_evaluations: int = 12,
    resolution: Decimal = Decimal("250"),
    min_amount: Decimal = MIN_AMOUNT,
    max_amount: Decimal = MAX_AMOUNT,
) -> SearchResult:
    """Evaluate the coarse grid (only amounts a provider supports), then bisect every adjacent pair
    where the ranking winner or the roi sign changes, until the gap is <= `resolution` or the
    evaluation budget (`max_evaluations`) is spent."""
    grid = sorted({Decimal(a) for a in amounts if min_amount <= Decimal(a) <= max_amount and supports(Decimal(a))})
    evals: dict[Decimal, Evaluation] = {}
    budget = max_evaluations
    for a in grid:
        if budget <= 0:
            break
        evals[a] = evaluate(a)
        budget -= 1

    tested = sorted(evals)
    pending: list[tuple[Decimal, Decimal]] = [
        (lo, hi) for lo, hi in zip(tested, tested[1:], strict=False) if _differs(evals[lo], evals[hi])
    ]
    boundaries: list[Boundary] = []

    def record(lo: Decimal, hi: Decimal, refined: bool) -> None:
        reason = _differs(evals[lo], evals[hi]) or "none"
        boundaries.append(
            Boundary(
                low=lo,
                high=hi,
                low_winner=evals[lo].winner,
                high_winner=evals[hi].winner,
                low_roi_sign=evals[lo].roi_sign,
                high_roi_sign=evals[hi].roi_sign,
                reason=reason,
                refined=refined,
            )
        )

    while pending:
        lo, hi = pending.pop(0)
        if hi - lo <= resolution or budget <= 0:
            record(lo, hi, refined=hi - lo <= resolution)
            continue
        mid = ((lo + hi) / 2).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        if mid <= lo or mid >= hi or not supports(mid):
            record(lo, hi, refined=False)
            continue
        evals[mid] = evaluate(mid)
        budget -= 1
        if _differs(evals[lo], evals[mid]):
            pending.append((lo, mid))
        if _differs(evals[mid], evals[hi]):
            pending.append((mid, hi))
        if not _differs(evals[lo], evals[mid]) and not _differs(evals[mid], evals[hi]):
            # non-monotonic change hidden between samples; keep the coarse boundary as information
            record(lo, hi, refined=False)

    boundaries.sort(key=lambda b: (b.low, b.high))
    return SearchResult(amounts_tested=sorted(evals), boundaries=boundaries, evaluations=evals)
