from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..models import utcnow
from ..schemas import HealthOut
from .deps import DbDep, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health", operation_id="health")
def health(db: DbDep, settings: SettingsDep) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # pragma: no cover - only on broken DB
        db_status = f"error: {type(exc).__name__}"
    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        data_mode=settings.data_mode,
        db=db_status,
        version=settings.app_version,
        server_time=utcnow(),
    )
