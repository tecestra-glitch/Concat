"""Smart polling state per source: adaptive interval, change detection, change log (module `watch`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..decimal_utils import fmt
from ..models import Change, Quote, Source, WatchState, utcnow
from ..schemas import ChangeOut, WatchStatusOut
from . import events as events_svc
from .quotes import context_identity

OK_STATUSES = {"ok", "degraded", "stale"}


def ensure_watch(
    session: Session,
    source: Source,
    *,
    now: datetime,
    data_mode: str,
    min_interval_s: int = 60,
    max_interval_s: int = 900,
) -> WatchState:
    ws = session.get(WatchState, source.id)
    if ws is None:
        interval = max(min_interval_s, min(source.poll_interval_s or 300, max_interval_s))
        ws = WatchState(
            source_id=source.id,
            enabled=True,
            interval_s=interval,
            min_interval_s=min_interval_s,
            max_interval_s=max_interval_s,
            next_run_at=now,
            status=source.health or "ok",
            data_mode=data_mode,
        )
        session.add(ws)
        session.flush()
    return ws


def is_due(ws: WatchState, now: datetime) -> bool:
    return bool(ws.enabled) and (ws.next_run_at is None or now >= ws.next_run_at)


def _side(prev: Decimal | None, cur: Decimal | None) -> str | None:
    if prev == cur:
        return None
    return f"{fmt(prev) if prev is not None else '—'} → {fmt(cur) if cur is not None else '—'}"


def detect_quote_changes(
    previous: list[Quote], current: list[Quote]
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Compare the latest quote per context before/after a capture. Returns (summary, before, after).

    `before`/`after` carry the structured context (`pair`, `city`, `source_id`, `series_key`) so alert rules
    match on fields, never on the human summary (B18)."""
    prev_by = {context_identity(q): q for q in previous}
    out = []
    for q in current:
        p = prev_by.get(context_identity(q))
        where = q.city or "digital"
        label = f"{q.base}/{q.quote} {where}" + (f" {fmt(q.amount_base)}" if q.amount_base is not None else "")
        after = _snapshot(q)
        if p is None:
            out.append((f"{label}: nova cotação (compra {fmt(q.buy) or '—'}, venda {fmt(q.sell) or '—'})", {}, after))
            continue
        parts = []
        b = _side(p.buy, q.buy)
        s = _side(p.sell, q.sell)
        if b:
            parts.append(f"compra {b}")
        if s:
            parts.append(f"venda {s}")
        if parts:
            out.append((f"{label} {'; '.join(parts)}", _snapshot(p), after))
    return out


def _snapshot(q: Quote) -> dict[str, Any]:
    return {
        "buy": fmt(q.buy),
        "sell": fmt(q.sell),
        "captured_at": q.captured_at.isoformat(),
        "series_key": q.series_key,
        "quote_id": q.id,
        "pair": f"{q.base}/{q.quote}",
        "city": q.city,
        "source_id": q.source_id,
        "modality": q.modality,
        "channel": q.channel,
    }


def record_change(
    session: Session,
    *,
    source_id: str,
    kind: str,
    summary: str,
    before: dict[str, Any],
    after: dict[str, Any],
    evidence_id: str | None,
    now: datetime,
    data_mode: str,
) -> Change:
    ch = Change(
        source_id=source_id,
        ts=now,
        kind=kind,
        summary=summary,
        before=before,
        after=after,
        evidence_id=evidence_id,
        data_mode=data_mode,
    )
    session.add(ch)
    session.flush()
    events_svc.append_event(
        session, "source.change", change_to_out(ch).model_dump(mode="json"), data_mode=data_mode, ts=now
    )
    return ch


def after_run(
    ws: WatchState,
    *,
    now: datetime,
    ok: bool,
    changed: bool | None,
    status: str,
    content_hash: str | None,
    etag: str | None = None,
    last_modified: str | None = None,
    backoff_max_s: int = 3600,
) -> None:
    """Adapt the interval: errors => exponential backoff; real change => shorter; unchanged => longer.
    `changed=None` means "nothing to compare against" (first capture): the interval is kept.
    `etag`/`last_modified` are the validators of the last response, reused by the next conditional GET."""
    ws.last_run_at = now
    ws.status = status
    if content_hash:
        ws.content_hash = content_hash
    if etag:
        ws.etag = etag
    if last_modified:
        ws.last_modified = last_modified
    if not ok:
        ws.errors_in_row = (ws.errors_in_row or 0) + 1
        ws.interval_s = min(max(ws.max_interval_s, backoff_max_s), ws.interval_s * 2)
    elif changed is None:
        ws.errors_in_row = 0
    elif changed:
        ws.errors_in_row = 0
        ws.last_change_at = now
        ws.interval_s = max(ws.min_interval_s, ws.interval_s // 2)
    else:
        ws.errors_in_row = 0
        ws.interval_s = min(ws.max_interval_s, int(ws.interval_s * 3 // 2))
    ws.next_run_at = now + timedelta(seconds=ws.interval_s)


def changes_24h(session: Session, source_id: str, now: datetime) -> int:
    return int(
        session.scalar(
            select(func.count(Change.id)).where(Change.source_id == source_id, Change.ts >= now - timedelta(hours=24))
        )
        or 0
    )


def status_out(session: Session, ws: WatchState, now: datetime | None = None) -> WatchStatusOut:
    now = now or utcnow()
    return WatchStatusOut(
        source_id=ws.source_id,
        enabled=ws.enabled,
        interval_s=ws.interval_s,
        min_interval_s=ws.min_interval_s,
        max_interval_s=ws.max_interval_s,
        next_run_at=ws.next_run_at,
        last_run_at=ws.last_run_at,
        last_change_at=ws.last_change_at,
        changes_24h=changes_24h(session, ws.source_id, now),
        errors_in_row=ws.errors_in_row,
        etag=ws.etag,
        last_modified=ws.last_modified,
        content_hash=ws.content_hash,
        status=ws.status,
    )


def list_states(session: Session, *, data_mode: str, now: datetime | None = None) -> list[WatchStatusOut]:
    now = now or utcnow()
    rows = session.scalars(select(WatchState).where(WatchState.data_mode == data_mode).order_by(WatchState.source_id))
    return [status_out(session, ws, now) for ws in rows]


def change_to_out(ch: Change) -> ChangeOut:
    return ChangeOut.model_validate(ch)


def list_changes(
    session: Session,
    *,
    data_mode: str,
    source: str | None = None,
    since: datetime | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> list[Change]:
    stmt = select(Change).where(Change.data_mode == data_mode)
    if source:
        stmt = stmt.where(Change.source_id == source)
    if since:
        stmt = stmt.where(Change.ts >= since)
    if kind:
        stmt = stmt.where(Change.kind == kind)
    return list(session.scalars(stmt.order_by(Change.ts.desc()).limit(limit)))
