"""Deterministic financial engine. Pure Python + Decimal (precision 28); no I/O, no rounding
until presentation (see `fronteira_fx.decimal_utils.fmt`)."""

from decimal import getcontext

getcontext().prec = 28

from .positions import Balance, Position  # noqa: E402
from .ranking import PHYSICAL_MARGIN, Candidate, Ranked, rank_opportunities  # noqa: E402
from .routes import Fee, RouteError, RouteResult, StepResult, StepSpec, simulate_route  # noqa: E402
from .search import DEFAULT_AMOUNTS, Boundary, Evaluation, SearchResult, adaptive_amount_search  # noqa: E402
from .volatility import Observation, VolatilityResult, compute_volatility  # noqa: E402

__all__ = [
    "DEFAULT_AMOUNTS",
    "PHYSICAL_MARGIN",
    "Balance",
    "Boundary",
    "Candidate",
    "Evaluation",
    "Fee",
    "Observation",
    "Position",
    "Ranked",
    "RouteError",
    "RouteResult",
    "SearchResult",
    "StepResult",
    "StepSpec",
    "VolatilityResult",
    "adaptive_amount_search",
    "compute_volatility",
    "rank_opportunities",
    "simulate_route",
]
