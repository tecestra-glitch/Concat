from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from ..models import Memory, utcnow
from ..schemas import MemoryCreate, MemoryKind, MemoryOut
from .deps import ApiKey, DataModeDep, DbDep

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", operation_id="remember", status_code=status.HTTP_201_CREATED, dependencies=[ApiKey])
def remember(body: MemoryCreate, db: DbDep, data_mode: DataModeDep) -> MemoryOut:
    now = utcnow()
    row = Memory(
        kind=body.kind,
        text=body.text,
        tags=list(body.tags),
        source=body.source,
        created_at=now,
        expires_at=now + timedelta(days=body.ttl_days) if body.ttl_days else None,
        data_mode=data_mode,
    )
    db.add(row)
    db.flush()
    return MemoryOut.model_validate(row)


@router.get("", operation_id="recall", summary="Text + tag search over memories, newest first")
def recall(
    db: DbDep,
    data_mode: DataModeDep,
    q: Annotated[str | None, Query(max_length=300)] = None,
    kind: Annotated[MemoryKind | None, Query()] = None,
    tag: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[MemoryOut]:
    now = utcnow()
    stmt = select(Memory).where(
        Memory.data_mode == data_mode, or_(Memory.expires_at.is_(None), Memory.expires_at > now)
    )
    if kind:
        stmt = stmt.where(Memory.kind == kind)
    if q:
        stmt = stmt.where(Memory.text.ilike(f"%{q}%"))
    rows = list(db.scalars(stmt.order_by(Memory.created_at.desc())))
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    return [MemoryOut.model_validate(r) for r in rows[:limit]]


@router.delete("/{memory_id}", operation_id="forget", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ApiKey])
def forget(memory_id: str, db: DbDep, data_mode: DataModeDep) -> None:
    row = db.get(Memory, memory_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="memória não encontrada")
    db.delete(row)
    db.flush()
