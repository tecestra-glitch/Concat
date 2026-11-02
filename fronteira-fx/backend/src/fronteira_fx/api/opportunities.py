from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import Channel, City, CycleOut, OpportunityKind, OpportunityOut
from ..services.cycles import find_cycles_for
from ..services.opportunities import list_opportunities, row_to_out
from .deps import DataModeDep, DbDep, SettingsDep

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", operation_id="list_opportunities", summary="Standing ranking (main + secondary)")
def get_opportunities(
    db: DbDep,
    data_mode: DataModeDep,
    capital: Annotated[Decimal | None, Query(gt=0)] = None,
    channel: Annotated[Channel | None, Query()] = None,
    city: Annotated[City | None, Query()] = None,
    kind: Annotated[OpportunityKind | None, Query()] = None,
) -> list[OpportunityOut]:
    rows = list_opportunities(db, data_mode=data_mode, capital=capital, channel=channel, city=city, kind=kind)
    return [row_to_out(r) for r in rows]


@router.get(
    "/cycles",
    operation_id="find_cycles",
    summary="Cycles in the position graph starting from parked balances (best ROI first)",
)
def get_cycles(
    db: DbDep,
    data_mode: DataModeDep,
    settings: SettingsDep,
    max_len: Annotated[int, Query(ge=2, le=6, description="máximo de arestas por ciclo")] = 4,
    min_roi: Annotated[Decimal | None, Query(description="ROI mínimo como string decimal, ex. 0.001")] = None,
    start: Annotated[str | None, Query(description="nó de partida, ex. BRL@nubank", max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[CycleOut]:
    return [
        CycleOut.model_validate(c)
        for c in find_cycles_for(
            db,
            data_mode=data_mode,
            max_len=max_len,
            min_roi=min_roi,
            start=start,
            limit=limit,
            lookback_s=settings.quotes_lookback_s,
        )
    ]
