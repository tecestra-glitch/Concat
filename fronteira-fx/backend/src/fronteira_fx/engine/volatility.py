"""Volatility per comparable context key on a 5-minute grid.

* windows: 1h / 24h, grid 300 s; one observation per grid cell (last wins)
* a re-captured quote with the same `declared_updated_at` is NOT a new observation
* returns = ln(mid_t / mid_{t-1}) between *adjacent* filled cells (unit: % per 5-min interval)
* sample standard deviation; fewer than `min_returns` valid returns => insufficient_data,
  or stale_input when the only reason is that captures repeat one declared timestamp
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from ..decimal_utils import fmt

WINDOWS: dict[str, int] = {"1h": 3600, "24h": 86400}
GRID_S = 300
MIN_RETURNS = 6
UNIT = "% por intervalo de 5 min"

Status = Literal["ok", "insufficient_data", "stale_input"]


@dataclass(frozen=True, slots=True)
class Observation:
    ts: datetime
    mid: Decimal
    declared_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VolatilityResult:
    key: str
    window: str
    grid_s: int
    returns_used: int
    min_returns: int
    stdev_pct_per_5m: Decimal | None
    coverage_pct: Decimal
    gaps: int
    status: Status
    observations_used: int = 0
    unit: str = UNIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "window": self.window,
            "grid_s": self.grid_s,
            "returns_used": self.returns_used,
            "min_returns": self.min_returns,
            "stdev_pct_per_5m": fmt(self.stdev_pct_per_5m),
            "coverage_pct": fmt(self.coverage_pct, 1),
            "gaps": self.gaps,
            "status": self.status,
            "unit": self.unit,
        }


def dedupe_observations(observations: Iterable[Observation]) -> tuple[list[Observation], int]:
    """Drop re-captures of the same declared quote. Returns (kept, raw_count)."""
    raw = sorted(observations, key=lambda o: o.ts)
    kept: list[Observation] = []
    seen_declared: set[datetime] = set()
    for o in raw:
        if o.declared_updated_at is not None:
            if o.declared_updated_at in seen_declared:
                continue
            seen_declared.add(o.declared_updated_at)
        kept.append(o)
    return kept, len(raw)


def compute_volatility(
    key: str,
    observations: Iterable[Observation],
    *,
    window: str,
    now: datetime,
    grid_s: int = GRID_S,
    min_returns: int = MIN_RETURNS,
) -> VolatilityResult:
    if window not in WINDOWS:
        raise ValueError(f"unknown window {window!r}; expected one of {sorted(WINDOWS)}")
    window_s = WINDOWS[window]
    # align cells to the absolute grid; the last cell is the one containing `now`
    epoch = int(now.timestamp())
    end_aligned = now if epoch % grid_s == 0 else now + timedelta(seconds=grid_s - epoch % grid_s)
    start = end_aligned - timedelta(seconds=window_s)
    in_window = [o for o in observations if start < o.ts <= now and o.mid is not None and o.mid > 0]
    kept, raw_count = dedupe_observations(in_window)

    expected_cells = window_s // grid_s
    cells: dict[int, Decimal] = {}
    for o in kept:
        elapsed = (o.ts - start).total_seconds()
        idx = int(-(-elapsed // grid_s)) - 1  # ceil - 1: (start, start+grid] -> cell 0
        idx = max(0, min(idx, expected_cells - 1))
        cells[idx] = o.mid  # observations are sorted by ts, so the last one in a cell wins

    filled = sorted(cells)
    coverage = (Decimal(len(filled)) * 100 / Decimal(expected_cells)) if expected_cells else Decimal(0)
    gaps = sum(1 for a, b in zip(filled, filled[1:], strict=False) if b - a > 1)

    returns: list[Decimal] = []
    for a, b in zip(filled, filled[1:], strict=False):
        if b - a == 1:
            returns.append((cells[b] / cells[a]).ln())

    n = len(returns)
    stale = raw_count >= 2 and len(kept) <= 1
    if n < min_returns:
        status: Status = "stale_input" if stale else "insufficient_data"
        return VolatilityResult(key, window, grid_s, n, min_returns, None, coverage, gaps, status, len(kept))

    mean = sum(returns, Decimal(0)) / Decimal(n)
    var = sum(((r - mean) ** 2 for r in returns), Decimal(0)) / Decimal(n - 1)
    stdev_pct = var.sqrt() * 100
    return VolatilityResult(key, window, grid_s, n, min_returns, stdev_pct, coverage, gaps, "ok", len(kept))
