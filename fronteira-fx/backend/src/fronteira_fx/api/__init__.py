"""All /v1 routers."""

from fastapi import APIRouter

from . import (
    accounts,
    alerts,
    candles,
    evidence,
    health,
    history,
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
):
    v1_router.include_router(module.router)

__all__ = ["v1_router"]
