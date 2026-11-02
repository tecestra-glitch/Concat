from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ..models import Source, utcnow
from ..schemas import SnapshotOut, SourceOut
from ..services import events as events_svc
from ..services.opportunities import list_opportunities, row_to_out
from ..services.quotes import latest_quotes, quote_to_out
from .deps import DataModeDep, DbDep, SettingsDep

router = APIRouter(tags=["stream"])


@router.get("/snapshot", operation_id="get_snapshot", summary="Full state + cursor to resume the stream from")
def get_snapshot(db: DbDep, data_mode: DataModeDep, settings: SettingsDep) -> SnapshotOut:
    cursor = events_svc.latest_cursor(db)
    quotes = latest_quotes(db, data_mode=data_mode, lookback_s=settings.quotes_lookback_s)
    sources = db.scalars(select(Source).where(Source.data_mode == data_mode).order_by(Source.id)).all()
    opps = list_opportunities(db, data_mode=data_mode)
    return SnapshotOut(
        cursor=str(cursor),
        quotes=[quote_to_out(q) for q in quotes],
        sources=[SourceOut.from_row(s) for s in sources],
        opportunities=[row_to_out(o) for o in opps],
        server_time=utcnow(),
        data_mode=data_mode,
    )
