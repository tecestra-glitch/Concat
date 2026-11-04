"""market: guid e trecho curto em news_items (investinglive) e tabela sentiment_readings (Fear & Greed)

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
    with op.batch_alter_table("news_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("guid", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("excerpt", sa.String(length=400), nullable=True))
        batch_op.create_index("ix_news_items_feed_guid", ["feed", "guid"], unique=False)

    op.create_table(
        "sentiment_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("observed_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("captured_at", fronteira_fx.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "observed_at", "data_mode", name="uq_sentiment_reading"),
    )
    with op.batch_alter_table("sentiment_readings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sentiment_readings_data_mode"), ["data_mode"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sentiment_readings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sentiment_readings_data_mode"))
    op.drop_table("sentiment_readings")

    with op.batch_alter_table("news_items", schema=None) as batch_op:
        batch_op.drop_index("ix_news_items_feed_guid")
        batch_op.drop_column("excerpt")
        batch_op.drop_column("guid")
