"""quotes.unit_note: VARCHAR(64) -> VARCHAR(255) (Postgres rejected the BCP reference note, 78 chars)

Revision ID: 0003_unit_note
Revises: 0002
Create Date: 2026-11-04 04:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003_unit_note'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('quotes', schema=None) as batch_op:
        batch_op.alter_column('unit_note', existing_type=sa.String(length=64), type_=sa.String(length=255),
                              existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('quotes', schema=None) as batch_op:
        batch_op.alter_column('unit_note', existing_type=sa.String(length=255), type_=sa.String(length=64),
                              existing_nullable=False)
