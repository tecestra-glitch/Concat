"""Internal routes for schedulers (not part of the public contract used by the frontend).

`POST /v1/internal/collect` runs one collector round when something outside the process calls it every few
minutes (the Supabase cron in serverless mode, see docs/deploy.md). It is only reachable with the cron secret:
without `CRON_SECRET` the route answers 404 as if it did not exist; a wrong or missing secret gets 401.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .deps import CollectorDep, SettingsDep, cron_secret_matches

router = APIRouter(prefix="/internal", tags=["internal"])


class CollectedSourceOut(BaseModel):
    id: str
    status: str  # adapter status: ok, degraded, blocked, stale, not_modified, ...
    health: str
    changed: bool  # a quote changed compared with the previous capture
    quotes_stored: int


class SkippedSourceOut(BaseModel):
    id: str
    reason: str  # short, from the server; never a provider message or body


class CollectRoundOut(BaseModel):
    duration_ms: int
    data_mode: str
    budget_s: float
    budget_exhausted: bool
    sources: list[CollectedSourceOut]
    skipped: list[SkippedSourceOut]
    tasks_processed: int
    events_pruned: int


def require_cron_secret(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.cron_secret_enabled:
        # Same body FastAPI gives for an unknown path: the route does not reveal that it exists.
        raise HTTPException(status_code=404, detail="Not Found")
    if not cron_secret_matches(settings, authorization):
        raise HTTPException(
            status_code=401,
            detail="segredo do agendador inválido ou ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/collect",
    operation_id="internal_collect",
    dependencies=[Depends(require_cron_secret)],
    summary="Uma rodada de coleta disparada de fora (agendador); sem navegador",
    responses={
        401: {"description": "segredo ausente ou errado (Authorization: Bearer <CRON_SECRET>)"},
        404: {"description": "CRON_SECRET não definido nesta instância"},
    },
)
async def internal_collect(collector: CollectorDep, settings: SettingsDep) -> CollectRoundOut:
    started = time.monotonic()
    result = await collector.run_round(budget_s=settings.collect_budget_s)
    return CollectRoundOut(
        duration_ms=round((time.monotonic() - started) * 1000),
        data_mode=result.data_mode,
        budget_s=settings.collect_budget_s,
        budget_exhausted=result.budget_exhausted,
        sources=[
            CollectedSourceOut(
                id=o.source_id,
                status=o.status,
                health=o.health,
                changed=any(c.kind == "quote_change" and c.before for c in o.changes),
                quotes_stored=o.quotes_stored,
            )
            for o in result.outcomes
        ],
        skipped=[SkippedSourceOut(id=s.source_id, reason=s.reason) for s in result.skipped],
        tasks_processed=result.tasks_processed,
        events_pruned=result.events_pruned,
    )
