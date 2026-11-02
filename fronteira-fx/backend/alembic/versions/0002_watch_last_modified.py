"""watch_states.last_modified: HTTP validator reused by the collector's conditional GET

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('watch_states', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_modified', sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('watch_states', schema=None) as batch_op:
        batch_op.drop_column('last_modified')
