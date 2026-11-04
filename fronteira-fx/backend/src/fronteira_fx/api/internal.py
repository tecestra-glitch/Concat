"""Internal routes for schedulers (not part of the public contract used by the frontend).

`POST /v1/internal/collect` runs one collector round when something outside the process calls it every few
minutes (the Supabase cron in serverless mode, see docs/deploy.md). With a body `{"sources": [...]}` it polls
only those sources, forced (the Supabase vigia asks after a change), still under the 60 s floor per source.

It is only reachable with the cron secret: without `CRON_SECRET` the route answers 404 as if it did not
exist; a wrong or missing secret gets 401.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from ..market.reads import ReadsRefresher
from .deps import CollectorDep, SettingsDep, cron_secret_matches

log = logging.getLogger("fronteira_fx.api.internal")
router = APIRouter(prefix="/internal", tags=["internal"])
MAX_SELECTED_SOURCES = 30


class CollectRequest(BaseModel):
    """Corpo opcional. Sem `sources` (ou corpo `{}`): a rodada normal de agendamento."""

    model_config = ConfigDict(extra="forbid")

    sources: list[str] | None = None  # ids conhecidos, até 30; só essas fontes, com agendamento forçado


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
        400: {"description": "lista `sources` com id desconhecido ou com mais de 30 ids"},
        401: {"description": "segredo ausente ou errado (Authorization: Bearer <CRON_SECRET>)"},
        404: {"description": "CRON_SECRET não definido nesta instância"},
    },
)
async def internal_collect(
    collector: CollectorDep, settings: SettingsDep, body: CollectRequest | None = None
) -> CollectRoundOut:
    started = time.monotonic()
    if body is not None and body.sources is not None:
        ids = list(dict.fromkeys(body.sources))  # sem repetidos, ordem preservada
        if len(body.sources) > MAX_SELECTED_SOURCES:
            raise HTTPException(status_code=400, detail=f"no máximo {MAX_SELECTED_SOURCES} fontes por chamada")
        if any(source_id not in collector.adapters() for source_id in ids):
            # sem eco: o id enviado não volta na resposta
            raise HTTPException(status_code=400, detail="fonte desconhecida na lista `sources`")
        result = await collector.run_selected(ids, budget_s=settings.collect_budget_s)
    else:
        result = await collector.run_round(budget_s=settings.collect_budget_s)
    # Sem worker residente (modo grátis), esta rodada periódica também recalcula triângulos e indicadores, com
    # frequência limitada no banco. A API continua só lendo market_reads. Falha aqui não derruba a coleta.
    try:
        ReadsRefresher(collector.session_factory, settings).maybe_refresh()
    except Exception:
        log.exception("leituras de mercado não recalculadas nesta rodada")
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
