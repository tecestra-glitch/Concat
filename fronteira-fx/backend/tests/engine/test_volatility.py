from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fronteira_fx.engine.volatility import Observation, compute_volatility

D = Decimal
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def obs(minutes_ago: int, mid: str, declared: datetime | None = "same_as_ts") -> Observation:
    ts = NOW - timedelta(minutes=minutes_ago)
    return Observation(ts=ts, mid=D(mid), declared_updated_at=ts if declared == "same_as_ts" else declared)


def test_ok_with_enough_adjacent_returns():
    mids = ["7300", "7310", "7305", "7320", "7315", "7330", "7325"]  # 7 cells => 6 returns
    observations = [obs(5 * (len(mids) - 1 - i), m) for i, m in enumerate(mids)]
    v = compute_volatility("k", observations, window="1h", now=NOW)
    assert v.status == "ok"
    assert v.returns_used == 6
    assert v.stdev_pct_per_5m is not None and v.stdev_pct_per_5m > 0
    assert v.coverage_pct == D(7) * 100 / D(12)
    assert v.gaps == 0
    assert v.unit == "% por intervalo de 5 min"


def test_five_returns_is_insufficient():
    mids = ["7300", "7310", "7305", "7320", "7315", "7330"]  # 6 cells => 5 returns
    observations = [obs(5 * (len(mids) - 1 - i), m) for i, m in enumerate(mids)]
    v = compute_volatility("k", observations, window="1h", now=NOW)
    assert v.status == "insufficient_data"
    assert v.returns_used == 5
    assert v.stdev_pct_per_5m is None


def test_recaptured_stale_quote_is_not_a_new_observation():
    declared = NOW - timedelta(hours=3)
    observations = [obs(5 * i, "7300", declared=declared) for i in range(12)]  # 12 captures, 1 declared value
    v = compute_volatility("k", observations, window="1h", now=NOW)
    assert v.status == "stale_input"
    assert v.returns_used == 0
    assert v.observations_used == 1


def test_gap_breaks_return_chain_and_is_counted():
    observations = [
        obs(55, "7300"),
        obs(50, "7310"),
        obs(45, "7305"),
        obs(35, "7320"),
        obs(30, "7315"),
        obs(25, "7330"),
        obs(20, "7325"),
        obs(15, "7340"),
    ]
    v = compute_volatility("k", observations, window="1h", now=NOW)
    assert v.gaps == 1
    assert v.returns_used == 6  # 2 adjacent returns before the gap + 4 after
    assert v.status == "ok"


def test_window_and_determinism():
    observations = [obs(5 * i, str(7300 + (i % 3) * 7)) for i in range(40)]
    a = compute_volatility("k", observations, window="24h", now=NOW)
    b = compute_volatility("k", list(reversed(observations)), window="24h", now=NOW)
    assert a == b
    assert a.grid_s == 300 and a.min_returns == 6
    with pytest.raises(ValueError):
        compute_volatility("k", observations, window="7d", now=NOW)
