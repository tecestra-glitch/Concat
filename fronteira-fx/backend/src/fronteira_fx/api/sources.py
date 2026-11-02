from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..models import Branch, Source
from ..schemas import BranchOut, SourceOut
from .deps import DataModeDep, DbDep

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", operation_id="list_sources", summary="List data sources and their health")
def list_sources(db: DbDep, data_mode: DataModeDep) -> list[SourceOut]:
    rows = db.scalars(select(Source).where(Source.data_mode == data_mode).order_by(Source.id)).all()
    return [SourceOut.from_row(r) for r in rows]


@router.get("/{source_id}/branches", operation_id="list_branches")
def list_branches(source_id: str, db: DbDep, data_mode: DataModeDep) -> list[BranchOut]:
    src = db.get(Source, source_id)
    if src is None or src.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="fonte não encontrada")
    rows = db.scalars(
        select(Branch).where(Branch.source_id == source_id, Branch.data_mode == data_mode).order_by(Branch.id)
    ).all()
    return [BranchOut.model_validate(r) for r in rows]
