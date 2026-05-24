"""add habit GoalType, habit_log MetricType, and weekly_target to goals

Revision ID: c3d5e7f9b1a2
Revises: a2c4e6b8d0f2
Create Date: 2026-05-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d5e7f9b1a2'
down_revision: Union[str, None] = 'a2c4e6b8d0f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend existing PostgreSQL enums — IF NOT EXISTS makes this re-runnable.
    # Note: ALTER TYPE ... ADD VALUE cannot run inside a transaction block in
    # older PostgreSQL versions, but TimescaleDB/PG14+ handles it fine here.
    op.execute("ALTER TYPE goaltype ADD VALUE IF NOT EXISTS 'habit'")
    op.execute("ALTER TYPE metrictype ADD VALUE IF NOT EXISTS 'habit_log'")

    op.add_column('goals', sa.Column('weekly_target', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('goals', 'weekly_target')
    # PostgreSQL does not support removing enum values without a full type rebuild.
