"""Memory endpoints over `models.Memory` (B10). Mirrors the reference `memory/service.py` semantics:
recall is text + tag search newest first (limit 1..100, default 20, see `docs/memoria.md`); the summary groups
non-expired memories by kind, newest first, trimming each item to 200 characters."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, or_, select
from sqlalchemy.sql import Select

from ..models import Memory, utcnow
from ..schemas import MemoryCreate, MemoryKind, MemoryOut, MemorySummary
from .deps import LIKE_ESCAPE, ApiKey, DataModeDep, DbDep, like_literal

router = APIRouter(prefix="/memory", tags=["memory"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_SUMMARY_LIMIT = 5
SUMMARY_ITEM_CHARS = 200
SUMMARY_SECTIONS: tuple[tuple[MemoryKind, str], ...] = (
    ("preference", "Preferências"),
    ("decision", "Decisões"),
    ("fact", "Fatos"),
    ("outcome", "Resultados"),
)


def _tag_filter(tag: str):
    """Whole-tag match inside the JSON array, in SQL on SQLite and Postgres alike.

    Tags are stored as a JSON list; the quoted JSON encoding of the tag (`"ueno"`) can only match a whole element.
    SQLite keeps the serializer's ASCII escapes (`"a\\u00e7..."`) while JSONB stores the text itself, so both forms
    are accepted when they differ."""
    column = cast(Memory.tags, String)
    variants = {json.dumps(tag), json.dumps(tag, ensure_ascii=False)}
    return or_(*(column.like(f"%{like_literal(v)}%", escape=LIKE_ESCAPE) for v in sorted(variants)))


def _active(data_mode: str) -> Select[tuple[Memory]]:
    now = utcnow()
    not_expired = or_(Memory.expires_at.is_(None), Memory.expires_at > now)
    return select(Memory).where(Memory.data_mode == data_mode, not_expired)


def _shorten(text: str, limit: int = SUMMARY_ITEM_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


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
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[MemoryOut]:
    stmt = _active(data_mode)
    if kind:
        stmt = stmt.where(Memory.kind == kind)
    if q:
        stmt = stmt.where(Memory.text.ilike(f"%{like_literal(q)}%", escape=LIKE_ESCAPE))
    if tag:
        stmt = stmt.where(_tag_filter(tag))
    rows = db.scalars(stmt.order_by(Memory.created_at.desc()).limit(limit))
    return [MemoryOut.model_validate(r) for r in rows]


@router.get("/summary", operation_id="memory_summary", summary="Compact digest of the active memories, by kind")
def memory_summary(
    db: DbDep,
    data_mode: DataModeDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="items per kind")] = DEFAULT_SUMMARY_LIMIT,
) -> MemorySummary:
    lines: list[str] = []
    for kind, label in SUMMARY_SECTIONS:
        items = list(
            db.scalars(_active(data_mode).where(Memory.kind == kind).order_by(Memory.created_at.desc()).limit(limit))
        )
        if items:
            lines.append(f"{label}: " + "; ".join(_shorten(m.text) for m in items))
    return MemorySummary(summary="\n".join(lines))


@router.delete("/{memory_id}", operation_id="forget", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ApiKey])
def forget(memory_id: str, db: DbDep, data_mode: DataModeDep) -> None:
    row = db.get(Memory, memory_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="memória não encontrada")
    db.delete(row)
    db.flush()
