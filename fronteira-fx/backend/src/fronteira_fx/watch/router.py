"""HTTP surface of the watch module: `APIRouter(prefix="/v1/watch")`.

The core mounts it with `app.include_router(router)` and injects its own service either with
`set_service(service)` or `app.dependency_overrides[get_service] = lambda: service`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .schemas import Change, ChangeKind, WatchStatus, WatchUpdate
from .service import UnknownSource, WatchService

router = APIRouter(prefix="/v1/watch", tags=["watch"])

_service: WatchService | None = None


def get_service() -> WatchService:
    """Default service (in-memory store + adapter registry). The core overrides this."""
    global _service
    if _service is None:
        _service = WatchService()
    return _service


def set_service(service: WatchService | None) -> None:
    global _service
    _service = service


ServiceDep = Annotated[WatchService, Depends(get_service)]
SourceId = Annotated[str, Path(min_length=1, max_length=64, description="Adapter/source id, e.g. `chaco`")]


def _not_found(source_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"fonte desconhecida: {source_id}")


@router.get("/sources", operation_id="watch_status", summary="Estado do monitoramento de cada fonte")
async def watch_status(service: ServiceDep) -> list[WatchStatus]:
    return service.statuses()


@router.post("/sources/{source_id}", operation_id="watch_update_source", summary="Ajuste manual (intervalo / ligar)")
async def watch_update_source(source_id: SourceId, body: WatchUpdate, service: ServiceDep) -> WatchStatus:
    try:
        return service.update_source(source_id, interval_s=body.interval_s, enabled=body.enabled)
    except UnknownSource:
        raise _not_found(source_id) from None


@router.post("/run/{source_id}", operation_id="trigger_poll", summary="Sondar a fonte agora")
async def trigger_poll(
    source_id: SourceId,
    service: ServiceDep,
    force: Annotated[bool, Query(description="Ignora ETag/If-Modified-Since (baixa a página de novo)")] = False,
) -> Change | None:
    try:
        outcome = await service.poll(source_id, force=force)
    except UnknownSource:
        raise _not_found(source_id) from None
    return outcome.change


@router.get("/changes", operation_id="list_changes", summary="Mudanças detectadas (mais recentes primeiro)")
async def list_changes(
    service: ServiceDep,
    source: Annotated[str | None, Query(max_length=64)] = None,
    from_: Annotated[datetime | None, Query(alias="from", description="ISO-8601; só mudanças a partir daqui")] = None,
    kind: Annotated[ChangeKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[Change]:
    return service.list_changes(source_id=source, since=from_, kind=kind, limit=limit)
