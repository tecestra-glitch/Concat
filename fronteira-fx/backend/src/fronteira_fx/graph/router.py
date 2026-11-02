"""GET /v1/opportunities/cycles — exposto via APIRouter; o core injeta o provedor de dados."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query

from .model import Edge
from .search import bellman_ford_negative_cycles, find_cycles

GraphProvider = Callable[[], tuple[list[Edge], Mapping[str, Decimal]]]

_provider: GraphProvider | None = None


def set_provider(p: GraphProvider) -> None:
    global _provider
    _provider = p


def get_provider() -> GraphProvider:
    if _provider is None:
        return lambda: ([], {})
    return _provider


router = APIRouter(prefix="/v1/opportunities", tags=["opportunities"])


@router.get("/cycles", operation_id="find_cycles", summary="Ciclos lucrativos no grafo de posições")
def find_cycles_route(
    max_len: int = Query(4, ge=2, le=8, description="máximo de arestas por ciclo"),
    min_roi: Decimal | None = Query(None, description="ROI mínimo (0.001 = 0,1 %)"),
    method: str = Query("enumeration", pattern="^(enumeration|bellman_ford)$"),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict[str, Any]]:
    edges, balances = get_provider()()
    if method == "bellman_ford":
        cycles = bellman_ford_negative_cycles(edges, balances, max_len=max_len)
        if min_roi is not None:
            cycles = [c for c in cycles if c.roi >= min_roi]
    else:
        cycles = find_cycles(edges, balances, max_len=max_len, min_roi=min_roi)
    return [c.to_dict() for c in cycles[:limit]]
