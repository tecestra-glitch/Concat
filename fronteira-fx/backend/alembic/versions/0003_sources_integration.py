"""sources.integration: how each source is reached (api_oficial | endpoint_interno | html | navegador)

Existing rows get 'html' as the server default; the collector overwrites it on the next
`ensure_sources` with the value declared by each adapter, so the default is only a placeholder.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('integration', sa.String(length=32), nullable=False, server_default='html')
        )


def downgrade() -> None:
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('integration')
