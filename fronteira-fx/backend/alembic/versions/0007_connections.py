"""connections e connection_statement_entries: conexões de conta (sem senha de banco; chave de corretora cifrada)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import fronteira_fx.models

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.JSON:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("institution", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("key_hint", sa.String(length=16), nullable=True),
        sa.Column("ciphertext", sa.Text(), nullable=True),
        sa.Column("balances", _json(), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column("last_synced_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=True),
        sa.Column("created_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("connections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_connections_institution"), ["institution"], unique=False)
        batch_op.create_index(batch_op.f("ix_connections_data_mode"), ["data_mode"], unique=False)

    op.create_table(
        "connection_statement_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", fronteira_fx.models.Money(precision=24, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("imported_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "fingerprint", name="uq_connection_entries_fingerprint"),
    )
    with op.batch_alter_table("connection_statement_entries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_connection_statement_entries_connection_id"), ["connection_id"])
        batch_op.create_index(batch_op.f("ix_connection_statement_entries_data_mode"), ["data_mode"])


def downgrade() -> None:
    with op.batch_alter_table("connection_statement_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_connection_statement_entries_data_mode"))
        batch_op.drop_index(batch_op.f("ix_connection_statement_entries_connection_id"))
    op.drop_table("connection_statement_entries")
    with op.batch_alter_table("connections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_connections_data_mode"))
        batch_op.drop_index(batch_op.f("ix_connections_institution"))
    op.drop_table("connections")
