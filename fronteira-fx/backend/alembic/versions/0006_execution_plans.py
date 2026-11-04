"""execution_plans e execution_steps: planos de execução (fase A, sem execução de movimentação)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import fronteira_fx.models

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.JSON:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "execution_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("start", sa.String(length=120), nullable=False),
        sa.Column("path", _json(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_in", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("amount_out_expected", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("gain_expected", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("gain_by_currency", _json(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("requires_declaration", sa.Boolean(), nullable=False),
        sa.Column("snapshot", _json(), nullable=False),
        sa.Column("quotes_as_of", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("quote_max_age_s", sa.Integer(), nullable=False),
        sa.Column("created_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("decided_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=True),
        sa.Column("completed_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=True),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("execution_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_execution_plans_data_mode"), ["data_mode"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_plans_status"), ["status"], unique=False)

    op.create_table(
        "execution_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("node_from", sa.String(length=120), nullable=False),
        sa.Column("node_to", sa.String(length=120), nullable=False),
        sa.Column("amount_in", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("amount_out_expected", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("actual_out", fronteira_fx.models.Money(precision=24, scale=8), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("done_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=True),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["execution_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "n", name="uq_execution_steps_plan_n"),
    )
    with op.batch_alter_table("execution_steps", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_execution_steps_data_mode"), ["data_mode"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_steps_plan_id"), ["plan_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("execution_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_execution_steps_plan_id"))
        batch_op.drop_index(batch_op.f("ix_execution_steps_data_mode"))
    op.drop_table("execution_steps")
    with op.batch_alter_table("execution_plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_execution_plans_status"))
        batch_op.drop_index(batch_op.f("ix_execution_plans_data_mode"))
    op.drop_table("execution_plans")
