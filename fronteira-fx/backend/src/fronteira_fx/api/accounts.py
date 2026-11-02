from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..models import Account, utcnow
from ..schemas import AccountCreate, AccountOut, AccountPatch
from .deps import ApiKey, DataModeDep, DbDep

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", operation_id="list_accounts")
def list_accounts(db: DbDep, data_mode: DataModeDep) -> list[AccountOut]:
    rows = db.scalars(
        select(Account).where(Account.data_mode == data_mode).order_by(Account.institution, Account.label)
    ).all()
    return [AccountOut.model_validate(r) for r in rows]


@router.post("", operation_id="create_account", status_code=status.HTTP_201_CREATED, dependencies=[ApiKey])
def create_account(body: AccountCreate, db: DbDep, data_mode: DataModeDep) -> AccountOut:
    row = Account(**body.model_dump(), data_mode=data_mode, updated_at=utcnow())
    db.add(row)
    db.flush()
    return AccountOut.model_validate(row)


@router.patch("/{account_id}", operation_id="update_account", dependencies=[ApiKey])
def update_account(account_id: str, body: AccountPatch, db: DbDep, data_mode: DataModeDep) -> AccountOut:
    row = db.get(Account, account_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="conta não encontrada")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    db.flush()
    return AccountOut.model_validate(row)
