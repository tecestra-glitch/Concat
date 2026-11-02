"""Ranking rules (docs/api-contract.md, "Regras do ranking").

1. Digital with net_gain > 0 (after known costs) enters the main ranking, however tiny.
2. Physical enters the main ranking only if roi_physical >= best comparable digital roi + 0.01
   (same capital, objective and horizon). Otherwise it goes to the secondary ranking with a reason.
3. confidence == incomplete is shown as an incomplete estimate, never as confirmed profit; incomplete
   digital candidates do not set the bar for physical ones.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import fmt
from .routes import StepResult

PHYSICAL_MARGIN = Decimal("0.01")

OpportunityKind = Literal["cycle", "remittance_saving", "purchase_saving"]
Channel = Literal["digital", "physical"]


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    title: str
    kind: OpportunityKind
    channel: Channel
    city: str | None
    capital: Decimal
    final_value: Decimal
    net_gain: Decimal
    roi: Decimal
    effective_rate: Decimal | None
    valuation_currency: str = "BRL"
    steps: tuple[StepResult, ...] = ()
    confidence: str = "quoted"
    pending_costs: tuple[str, ...] = ()
    objective: str = "cycle"
    horizon: str = "default"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def group_key(self) -> tuple[Decimal, str, str]:
        return (self.capital, self.objective, self.horizon)


@dataclass(frozen=True, slots=True)
class Ranked:
    candidate: Candidate
    rank: int
    in_main_ranking: bool
    ranking_reason: str
    comparable_best_digital_roi: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        c = self.candidate
        return {
            "id": c.id,
            "title": c.title,
            "kind": c.kind,
            "channel": c.channel,
            "city": c.city,
            "capital_brl": fmt(c.capital),
            "final_value_brl": fmt(c.final_value),
            "net_gain_brl": fmt(c.net_gain),
            "roi": fmt(c.roi),
            "effective_rate": fmt(c.effective_rate),
            "valuation_currency": c.valuation_currency,
            "steps": [s.to_dict() for s in c.steps],
            "confidence": c.confidence,
            "pending_costs": list(c.pending_costs),
            "in_main_ranking": self.in_main_ranking,
            "ranking_reason": self.ranking_reason,
            "comparable_best_digital_roi": fmt(self.comparable_best_digital_roi),
            "rank": self.rank,
        }


def best_comparable_digital_roi(cands: Iterable[Candidate]) -> Decimal | None:
    """Best ROI among digital candidates with positive net gain and non-incomplete confidence."""
    best: Decimal | None = None
    for c in cands:
        if c.channel != "digital" or c.net_gain <= 0 or c.confidence == "incomplete":
            continue
        if best is None or c.roi > best:
            best = c.roi
    return best


def _classify(c: Candidate, best_digital: Decimal | None) -> tuple[bool, str]:
    incomplete = " (estimativa incompleta: faltam custos)" if c.confidence == "incomplete" else ""
    if c.channel == "digital":
        if c.net_gain > 0:
            return True, "digital com ganho líquido positivo" + incomplete
        return False, "digital sem ganho líquido após custos conhecidos" + incomplete
    # physical
    if c.net_gain <= 0:
        return False, "físico sem ganho líquido após custos conhecidos" + incomplete
    if best_digital is None:
        return True, "físico com ganho líquido positivo; sem digital comparável" + incomplete
    threshold = best_digital + PHYSICAL_MARGIN
    if c.roi >= threshold:
        return (
            True,
            f"físico supera o melhor digital comparável em >= 1 p.p. (roi {fmt(c.roi)} >= {fmt(threshold)})"
            + incomplete,
        )
    return (
        False,
        f"físico abaixo do limiar: roi {fmt(c.roi)} < melhor digital {fmt(best_digital)} + 0.01" + incomplete,
    )


def rank_opportunities(candidates: Iterable[Candidate]) -> list[Ranked]:
    """Main ranking first (by roi desc), then secondary ranking (by roi desc). Deterministic."""
    cands = list(candidates)
    groups: dict[tuple[Decimal, str, str], list[Candidate]] = {}
    for c in cands:
        groups.setdefault(c.group_key, []).append(c)
    best_by_group = {k: best_comparable_digital_roi(v) for k, v in groups.items()}

    classified: list[tuple[Candidate, bool, str, Decimal | None]] = []
    for c in cands:
        best = best_by_group[c.group_key]
        in_main, reason = _classify(c, best)
        classified.append((c, in_main, reason, best))

    def sort_key(item: tuple[Candidate, bool, str, Decimal | None]) -> tuple:
        c, in_main, _, _ = item
        return (0 if in_main else 1, -c.roi, -c.net_gain, c.title, c.id)

    classified.sort(key=sort_key)
    return [
        Ranked(candidate=c, rank=i, in_main_ranking=in_main, ranking_reason=reason, comparable_best_digital_roi=best)
        for i, (c, in_main, reason, best) in enumerate(classified, start=1)
    ]
