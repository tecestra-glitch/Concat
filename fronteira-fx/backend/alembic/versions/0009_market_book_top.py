"""market_book_top: último topo do livro (bookTicker) por par, gravado em lote pelo stream da Binance

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-04 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import fronteira_fx.models

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_book_top",
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.Column("instrument", sa.String(length=32), nullable=False),
        sa.Column("bid", fronteira_fx.models.Money(), nullable=False),
        sa.Column("bid_qty", fronteira_fx.models.Money(), nullable=False),
        sa.Column("ask", fronteira_fx.models.Money(), nullable=False),
        sa.Column("ask_qty", fronteira_fx.models.Money(), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("captured_at", fronteira_fx.models.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "data_mode"),
    )


def downgrade() -> None:
    op.drop_table("market_book_top")
