"""fx_reference_quotes e reference_api_usage: referências de câmbio (nunca executáveis) e contador mensal da OXR

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import fronteira_fx.models

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_reference_quotes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("price", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("observed_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("collected_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("referencia", sa.Boolean(), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "instrument", "observed_at", "data_mode", name="uq_fx_reference_quote"),
    )
    with op.batch_alter_table("fx_reference_quotes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_fx_reference_quotes_instrument"), ["instrument"], unique=False)
        batch_op.create_index(batch_op.f("ix_fx_reference_quotes_source"), ["source"], unique=False)
        batch_op.create_index(batch_op.f("ix_fx_reference_quotes_data_mode"), ["data_mode"], unique=False)

    op.create_table(
        "reference_api_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "period", name="uq_reference_api_usage"),
    )


def downgrade() -> None:
    op.drop_table("reference_api_usage")
    with op.batch_alter_table("fx_reference_quotes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fx_reference_quotes_data_mode"))
        batch_op.drop_index(batch_op.f("ix_fx_reference_quotes_source"))
        batch_op.drop_index(batch_op.f("ix_fx_reference_quotes_instrument"))
    op.drop_table("fx_reference_quotes")
