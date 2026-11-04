"""market: leituras calculadas no worker (triângulos e indicadores) na tabela market_reads

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-04 19:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import fronteira_fx.models

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_reads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("computed_at", fronteira_fx.models.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "key", "data_mode", name="uq_market_read"),
    )
    with op.batch_alter_table("market_reads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_market_reads_data_mode"), ["data_mode"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("market_reads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_market_reads_data_mode"))
    op.drop_table("market_reads")
