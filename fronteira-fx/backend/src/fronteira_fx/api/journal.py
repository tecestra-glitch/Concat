from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from ..models import JournalEntry, utcnow
from ..schemas import JournalEntryCreate, JournalEntryOut
from .deps import ApiKey, DataModeDep, DbDep

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", operation_id="list_journal")
def list_journal(db: DbDep, data_mode: DataModeDep) -> list[JournalEntryOut]:
    rows = db.scalars(
        select(JournalEntry).where(JournalEntry.data_mode == data_mode).order_by(JournalEntry.ts.desc())
    ).all()
    return [JournalEntryOut.model_validate(r) for r in rows]


@router.post("", operation_id="create_journal_entry", status_code=status.HTTP_201_CREATED, dependencies=[ApiKey])
def create_journal_entry(body: JournalEntryCreate, db: DbDep, data_mode: DataModeDep) -> JournalEntryOut:
    row = JournalEntry(
        ts=body.ts or utcnow(),
        kind=body.kind,
        text=body.text,
        amounts=[a.model_dump(mode="json") for a in body.amounts],
        account_ids=list(body.account_ids),
        data_mode=data_mode,
    )
    db.add(row)
    db.flush()
    return JournalEntryOut.model_validate(row)
