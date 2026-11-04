"""All /v1 routers."""

from fastapi import APIRouter, Depends

from . import (
    accounts,
    alerts,
    candles,
    connections,
    evidence,
    health,
    history,
    institutions,
    internal,
    journal,
    market,
    market_reads,
    memory,
    opportunities,
    plans,
    quotes,
    rag,
    simulations,
    snapshot,
    sources,
    stream,
    watch,
)
from .deps import require_instance_mode

v1_router = APIRouter(prefix="/v1")
for module in (
    health,
    sources,
    quotes,
    history,
    candles,
    accounts,
    connections,
    institutions,
    simulations,
    opportunities,
    evidence,
    journal,
    plans,
    snapshot,
    stream,
    watch,
    alerts,
    rag,
    memory,
    internal,
    market,
    market_reads,
):
    # SEC-01: `?data_mode=` that differs from the instance mode → 409. Health stays open: it is how a
    # client discovers which mode this instance serves.
    guard = [] if module is health else [Depends(require_instance_mode)]
    v1_router.include_router(module.router, dependencies=guard)

__all__ = ["v1_router"]
