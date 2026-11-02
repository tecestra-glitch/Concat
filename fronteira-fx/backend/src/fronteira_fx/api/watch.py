from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..models import Source
from ..schemas import ChangeKind, ChangeOut, WatchPatch, WatchStatusOut
from ..services import watch as watch_svc
from ..services.collector import RateLimited, UnknownSource, WrongDataMode
from .deps import ApiKey, CollectorDep, DataModeDep, DbDep, SettingsDep

router = APIRouter(prefix="/watch", tags=["watch"])


@router.get("/sources", operation_id="watch_status", summary="Smart-polling status per source")
def watch_status(db: DbDep, data_mode: DataModeDep) -> list[WatchStatusOut]:
    return watch_svc.list_states(db, data_mode=data_mode)


@router.post(
    "/sources/{source_id}",
    operation_id="update_watch",
    dependencies=[ApiKey],
    summary="Manual adjustment of a source's polling (interval / enabled)",
)
def update_watch(
    source_id: str, body: WatchPatch, db: DbDep, data_mode: DataModeDep, settings: SettingsDep
) -> WatchStatusOut:
    src = db.get(Source, source_id)
    if src is None or src.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="fonte não encontrada")
    now = watch_svc.utcnow()
    ws = watch_svc.ensure_watch(
        db,
        src,
        now=now,
        data_mode=data_mode,
        min_interval_s=settings.watch_min_interval_s,
        max_interval_s=settings.watch_max_interval_s,
    )
    data = body.model_dump(exclude_unset=True)
    if "min_interval_s" in data:
        ws.min_interval_s = data["min_interval_s"]
    if "max_interval_s" in data:
        ws.max_interval_s = max(data["max_interval_s"], ws.min_interval_s)
    if "enabled" in data:
        ws.enabled = data["enabled"]
    if "interval_s" in data:
        ws.interval_s = data["interval_s"]
        ws.next_run_at = now  # apply right away
    ws.interval_s = max(ws.min_interval_s, min(ws.interval_s, ws.max_interval_s))
    src.next_poll_at = ws.next_run_at
    db.flush()
    return watch_svc.status_out(db, ws, now)


@router.post(
    "/run/{source_id}",
    operation_id="trigger_poll",
    dependencies=[ApiKey],
    summary="Poll one source now; returns the first detected Change or null",
    responses={
        404: {"description": "fonte sem adaptador registrado"},
        409: {"description": "instância fora do modo real (simulation/demo não consultam provedores)"},
        429: {"description": "fonte sondada há menos de 60 s; `Retry-After` em segundos"},
    },
)
async def trigger_poll(source_id: str, collector: CollectorDep) -> ChangeOut | None:
    try:
        return await collector.poll_now(source_id)
    except UnknownSource as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WrongDataMode as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": str(exc.retry_after_s)}) from exc


@router.get("/changes", operation_id="list_changes")
def list_changes(
    db: DbDep,
    data_mode: DataModeDep,
    source: Annotated[str | None, Query(max_length=64)] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    kind: Annotated[ChangeKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ChangeOut]:
    rows = watch_svc.list_changes(db, data_mode=data_mode, source=source, since=from_, kind=kind, limit=limit)
    return [watch_svc.change_to_out(r) for r in rows]
