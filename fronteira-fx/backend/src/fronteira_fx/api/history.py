from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import HistorySeries, VolatilityOut, Window
from ..services.history import history_series, volatility_for_key
from .deps import DataModeDep, DbDep

router = APIRouter(tags=["history"])


@router.get("/history", operation_id="get_history", summary="Resampled history for a series key")
def get_history(
    db: DbDep,
    data_mode: DataModeDep,
    key: Annotated[str, Query(min_length=3, max_length=255, description="e.g. chaco:CDE:USD/PYG:cash")],
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    grid: Annotated[int, Query(ge=1, le=86400)] = 300,
) -> HistorySeries:
    return history_series(db, key, data_mode=data_mode, start=from_, end=to, grid_s=grid)


@router.get("/volatility", operation_id="get_volatility")
def get_volatility(
    db: DbDep,
    data_mode: DataModeDep,
    key: Annotated[str, Query(min_length=3, max_length=255)],
    window: Annotated[Window, Query()] = "1h",
) -> VolatilityOut:
    return VolatilityOut.model_validate(volatility_for_key(db, key, window=window, data_mode=data_mode).to_dict())
