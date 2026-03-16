"""add created_at to cook_logs

Revision ID: a1b2c3d4e5f6
Revises: 7b82ff03700a
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7b82ff03700a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'cook_logs',
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        )
    )


def downgrade() -> None:
    op.drop_column('cook_logs', 'created_at')
