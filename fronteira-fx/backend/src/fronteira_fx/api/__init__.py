"""All /v1 routers."""

from fastapi import APIRouter, Depends

from . import (
    accounts,
    alerts,
    candles,
    evidence,
    health,
    history,
    internal,
    journal,
    memory,
    opportunities,
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
    simulations,
    opportunities,
    evidence,
    journal,
    snapshot,
    stream,
    watch,
    alerts,
    rag,
    memory,
    internal,
):
    # SEC-01: `?data_mode=` that differs from the instance mode → 409. Health stays open: it is how a
    # client discovers which mode this instance serves.
    guard = [] if module is health else [Depends(require_instance_mode)]
    v1_router.include_router(module.router, dependencies=guard)

__all__ = ["v1_router"]
