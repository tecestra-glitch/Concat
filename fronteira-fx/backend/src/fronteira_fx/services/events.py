"""Append-only event stream with integer cursors (the SSE `id`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import QuoteEvent, utcnow


class CursorExpired(Exception):
    """The client's cursor points before the retained window: it must take a new snapshot."""

    def __init__(self, cursor: int, oldest: int) -> None:
        super().__init__(f"cursor {cursor} expired; oldest retained event is {oldest}")
        self.cursor = cursor
        self.oldest = oldest


def parse_cursor(raw: str | int | None) -> int | None:
    if raw is None or raw == "":
        return None
    value = int(str(raw).strip())
    if value < 0:
        raise ValueError("cursor must be >= 0")
    return value


def append_event(
    session: Session, type_: str, payload: dict[str, Any], *, data_mode: str, ts: datetime | None = None
) -> QuoteEvent:
    ev = QuoteEvent(type=type_, payload=payload, data_mode=data_mode, ts=ts or utcnow())
    session.add(ev)
    session.flush()  # assigns the autoincrement cursor
    return ev


def latest_cursor(session: Session) -> int:
    return int(session.scalar(select(func.max(QuoteEvent.id))) or 0)


def oldest_cursor(session: Session) -> int | None:
    value = session.scalar(select(func.min(QuoteEvent.id)))
    return int(value) if value is not None else None


def check_cursor(session: Session, cursor: int) -> None:
    """Raise CursorExpired when events after `cursor` may have been pruned."""
    oldest = oldest_cursor(session)
    if oldest is None:
        return  # nothing retained: any cursor is as good as "latest"
    if cursor < oldest - 1:
        raise CursorExpired(cursor, oldest)


def replay(session: Session, after: int, *, data_mode: str, limit: int = 500) -> list[QuoteEvent]:
    stmt = (
        select(QuoteEvent)
        .where(QuoteEvent.id > after, QuoteEvent.data_mode == data_mode)
        .order_by(QuoteEvent.id.asc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def prune(session: Session, *, max_events: int, max_age_s: int, now: datetime | None = None) -> int:
    """Delete events older than `max_age_s` or beyond the newest `max_events`. Returns rows deleted."""
    now = now or utcnow()
    deleted = 0
    cutoff = now - timedelta(seconds=max_age_s)
    res = session.execute(delete(QuoteEvent).where(QuoteEvent.ts < cutoff))
    deleted += res.rowcount or 0
    total = int(session.scalar(select(func.count(QuoteEvent.id))) or 0)
    if total > max_events:
        keep_from = session.scalar(select(QuoteEvent.id).order_by(QuoteEvent.id.desc()).offset(max_events - 1).limit(1))
        if keep_from is not None:
            res = session.execute(delete(QuoteEvent).where(QuoteEvent.id < keep_from))
            deleted += res.rowcount or 0
    return deleted


def to_stream_event(ev: QuoteEvent) -> dict[str, Any]:
    return {"id": str(ev.id), "type": ev.type, "ts": ev.ts.isoformat(), "payload": ev.payload or {}}


def heartbeat_event(cursor: int, ts: datetime | None = None) -> dict[str, Any]:
    return {"id": str(cursor), "type": "heartbeat", "ts": (ts or utcnow()).isoformat(), "payload": {}}
