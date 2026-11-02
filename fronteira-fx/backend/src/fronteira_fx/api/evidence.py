from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from ..models import Evidence
from ..schemas import EvidenceOut
from .deps import LIKE_ESCAPE, DataModeDep, DbDep, like_literal

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("", operation_id="search_evidence", summary="Evidence records (what was fetched, hash, excerpt)")
def search_evidence(
    db: DbDep,
    data_mode: DataModeDep,
    source: Annotated[str | None, Query(max_length=64)] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="literal substring of the excerpt (case-insensitive)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EvidenceOut]:
    stmt = select(Evidence).where(Evidence.data_mode == data_mode)
    if source:
        stmt = stmt.where(Evidence.source_id == source)
    if from_:
        stmt = stmt.where(Evidence.captured_at >= from_)
    if q:
        stmt = stmt.where(Evidence.excerpt.ilike(f"%{like_literal(q)}%", escape=LIKE_ESCAPE))
    stmt = stmt.order_by(Evidence.captured_at.desc()).limit(limit)
    return [EvidenceOut.model_validate(r) for r in db.scalars(stmt)]


@router.get("/{evidence_id}", operation_id="get_evidence")
def get_evidence(evidence_id: str, db: DbDep, data_mode: DataModeDep) -> EvidenceOut:
    row = db.get(Evidence, evidence_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="evidência não encontrada")
    return EvidenceOut.model_validate(row)
