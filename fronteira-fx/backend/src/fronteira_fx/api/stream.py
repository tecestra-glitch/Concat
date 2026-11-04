"""SSE stream of quote/source/opportunity events.

* `Last-Event-ID` header or `?cursor=` selects where replay starts (events with id > cursor).
* Every event carries `id:` (the cursor). Heartbeats carry the current cursor too.
* A cursor older than the retention window => 410 Gone: the client takes a new /v1/snapshot.
* Connections are bounded (STREAM_MAX_DURATION_S, default 55 s) and closed cleanly so clients
  resume with their last id. No `event:` field is sent, so `EventSource.onmessage` receives
  everything; the JSON `type` field distinguishes event kinds.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from ..services import events as events_svc
from .deps import DbDep, SettingsDep

router = APIRouter(tags=["stream"])


def resolve_cursor(
    db: DbDep,
    cursor: Annotated[str | None, Query(description="replay events with id > cursor")] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> int:
    """Query param wins over the header. Validates retention *before* the response starts."""
    raw = cursor if cursor not in (None, "") else last_event_id
    try:
        value = events_svc.parse_cursor(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="cursor inválido") from exc
    if value is None:
        return events_svc.latest_cursor(db)  # live tail only
    try:
        events_svc.check_cursor(db, value)
    except events_svc.CursorExpired as exc:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "cursor_expired",
                "cursor": exc.cursor,
                "oldest": exc.oldest,
                "hint": "refaça GET /v1/snapshot e reconecte com o novo cursor",
            },
        ) from exc
    return value


CursorDep = Annotated[int, Depends(resolve_cursor)]


@router.get(
    "/stream",
    response_class=EventSourceResponse,
    operation_id="stream_events",
    responses={410: {"description": "cursor expirado: refazer snapshot"}},
)
async def stream_events(request: Request, settings: SettingsDep, cursor: CursorDep) -> AsyncIterable[ServerSentEvent]:
    factory = request.app.state.session_factory
    data_mode = settings.data_mode
    batch = settings.stream_batch

    def fetch(after: int) -> list[dict]:
        session = factory()
        try:
            return [
                events_svc.to_stream_event(e)
                for e in events_svc.replay(session, after, data_mode=data_mode, limit=batch)
            ]
        finally:
            session.close()

    started = time.monotonic()
    last_sent = started
    deadline = started + settings.stream_max_duration_s
    yield ServerSentEvent(comment="connected", retry=settings.stream_retry_ms)
    while time.monotonic() < deadline:
        if await request.is_disconnected():
            return
        for ev in await run_in_threadpool(fetch, cursor):
            cursor = int(ev["id"])
            yield ServerSentEvent(data=ev, id=ev["id"])
            last_sent = time.monotonic()
        now = time.monotonic()
        if now - last_sent >= settings.stream_heartbeat_s:
            yield ServerSentEvent(data=events_svc.heartbeat_event(cursor), id=str(cursor))
            last_sent = now
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(settings.stream_poll_s, remaining))
    yield ServerSentEvent(comment="max duration reached; reconnect with Last-Event-ID", id=str(cursor))
