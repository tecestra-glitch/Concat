"""Regras de conexões que tocam no banco: leitura por modo de dados, importação de extrato e saldo da conta manual."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Connection, StatementEntry, utcnow
from .exchanges import KeyCheck
from .schemas import ConnectionOut
from .statement import Transaction, fingerprint


def get_connection_or_404(db: Session, connection_id: str, data_mode: str) -> Connection:
    row = db.get(Connection, connection_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conexão não encontrada")
    return row


def check_linked_account(db: Session, account_id: str | None, data_mode: str) -> Account | None:
    if account_id is None:
        return None
    account = db.get(Account, account_id)
    if account is None or account.data_mode != data_mode:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="conta vinculada não existe")
    return account


def balances_snapshot(check: KeyCheck) -> list[dict[str, str]]:
    return [{"asset": b.asset, "free": str(b.free), "locked": str(b.locked)} for b in check.balances]


def to_out(row: Connection) -> ConnectionOut:
    return ConnectionOut(
        id=row.id,
        institution=row.institution,
        label=row.label,
        kind=row.kind,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        data_mode=row.data_mode,
        account_id=row.account_id,
        key_hint=row.key_hint,
        balances=row.balances,  # type: ignore[arg-type]
        last_error=row.last_error,
        last_synced_at=row.last_synced_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@dataclass(frozen=True)
class ImportResult:
    imported: int
    duplicates: int
    balance_delta: Decimal
    account_id: str | None
    account_balance_free: Decimal | None


def import_transactions(db: Session, connection: Connection, transactions: list[Transaction]) -> ImportResult:
    """Grava só lançamentos novos (fingerprint). Se a conexão tem conta manual vinculada, o saldo livre dela recebe a
    soma dos lançamentos novos. Moeda diferente da conta recusa tudo, sem gravar nada."""
    account = check_linked_account(db, connection.account_id, connection.data_mode)
    if account is not None:
        wrong = sorted({t.currency for t in transactions if t.currency != account.currency})
        if wrong:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"moeda do extrato ({', '.join(wrong)}) difere da conta vinculada ({account.currency})",
            )

    seen_bases: dict[str, int] = {}
    prepared: list[tuple[str, Transaction]] = []
    for tx in transactions:
        base = tx.fitid or f"{tx.occurred_on}|{tx.amount}|{tx.currency}|{tx.description}"
        occurrence = seen_bases.get(base, 0)
        seen_bases[base] = occurrence + 1
        prepared.append((fingerprint(connection.id, tx, occurrence), tx))

    existing = set(
        db.scalars(select(StatementEntry.fingerprint).where(StatementEntry.connection_id == connection.id)).all()
    )
    fresh = [(fp, tx) for fp, tx in prepared if fp not in existing]
    now = utcnow()
    for fp, tx in fresh:
        db.add(
            StatementEntry(
                connection_id=connection.id,
                occurred_on=tx.occurred_on,
                description=tx.description,
                amount=tx.amount,
                currency=tx.currency,
                fingerprint=fp,
                imported_at=now,
                data_mode=connection.data_mode,
            )
        )
    delta = sum((tx.amount for _, tx in fresh), Decimal(0))
    balance_after: Decimal | None = None
    if account is not None:
        account.balance_free = (account.balance_free or Decimal(0)) + delta
        account.updated_at = now
        balance_after = account.balance_free
    connection.updated_at = now
    db.flush()
    return ImportResult(
        imported=len(fresh),
        duplicates=len(prepared) - len(fresh),
        balance_delta=delta,
        account_id=connection.account_id,
        account_balance_free=balance_after,
    )
