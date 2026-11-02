"""History (grid resampling) and volatility per series key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engine.volatility import WINDOWS, Observation, VolatilityResult, compute_volatility
from ..models import Quote, utcnow
from ..schemas import HistoryPoint, HistorySeries
from .candles import LIKE_ESCAPE, like_prefix


def _mid(buy: Decimal | None, sell: Decimal | None) -> Decimal | None:
    if buy is not None and sell is not None:
        return (buy + sell) / 2
    return buy if buy is not None else sell


def _bucket_start(ts: datetime, grid_s: int) -> datetime:
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % grid_s, tz=UTC)


def _key_filter(key: str):
    """Exact series key, or a contract-style prefix (e.g. `chaco:CDE:USD/PYG:cash`) matching every
    series below it (branches / amounts / contexts). Same LIKE escaping as `services.candles.key_filter`."""
    return (Quote.series_key == key) | Quote.series_key.like(like_prefix(key), escape=LIKE_ESCAPE)


def history_series(
    session: Session,
    key: str,
    *,
    data_mode: str,
    start: datetime | None = None,
    end: datetime | None = None,
    grid_s: int = 300,
) -> HistorySeries:
    end = end or utcnow()
    start = start or end - timedelta(hours=24)
    grid_s = max(int(grid_s), 1)
    stmt = (
        select(Quote)
        .where(_key_filter(key), Quote.data_mode == data_mode, Quote.captured_at >= start, Quote.captured_at <= end)
        .order_by(Quote.captured_at.asc(), Quote.id.asc())
    )
    buckets: dict[datetime, Quote] = {}
    for q in session.scalars(stmt):
        buckets[_bucket_start(q.captured_at, grid_s)] = q  # last observation in the cell wins
    points = [HistoryPoint(t=t, buy=q.buy, sell=q.sell, mid=_mid(q.buy, q.sell)) for t, q in sorted(buckets.items())]
    return HistorySeries(key=key, points=points)


def observations_for_key(
    session: Session, key: str, *, data_mode: str, start: datetime, end: datetime
) -> list[Observation]:
    stmt = (
        select(Quote)
        .where(_key_filter(key), Quote.data_mode == data_mode, Quote.captured_at > start, Quote.captured_at <= end)
        .order_by(Quote.captured_at.asc(), Quote.id.asc())
    )
    obs: list[Observation] = []
    for q in session.scalars(stmt):
        mid = _mid(q.buy, q.sell)
        if mid is None:
            continue
        obs.append(Observation(ts=q.captured_at, mid=mid, declared_updated_at=q.declared_updated_at))
    return obs


def volatility_for_key(
    session: Session, key: str, *, window: str, data_mode: str, now: datetime | None = None, grid_s: int = 300
) -> VolatilityResult:
    now = now or utcnow()
    start = now - timedelta(seconds=WINDOWS[window])
    obs = observations_for_key(session, key, data_mode=data_mode, start=start, end=now)
    return compute_volatility(key, obs, window=window, now=now, grid_s=grid_s)
