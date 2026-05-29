"""add template_id and habit fields to goals

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-28 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE habittype AS ENUM ('count', 'duration', 'consistency', 'volume'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE habitperiod AS ENUM ('day', 'week', 'month'); EXCEPTION WHEN duplicate_object THEN null; END $$")

    op.add_column('goals', sa.Column('template_id', sa.String(100), nullable=True))
    op.add_column('goals', sa.Column(
        'habit_type',
        sa.Enum('count', 'duration', 'consistency', 'volume', name='habittype', create_type=False),
        nullable=True,
    ))
    op.add_column('goals', sa.Column('habit_unit', sa.String(50), nullable=True))
    op.add_column('goals', sa.Column(
        'habit_period',
        sa.Enum('day', 'week', 'month', name='habitperiod', create_type=False),
        nullable=True,
    ))
    op.add_column('goals', sa.Column('capture_keywords', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('goals', 'capture_keywords')
    op.drop_column('goals', 'habit_period')
    op.drop_column('goals', 'habit_unit')
    op.drop_column('goals', 'habit_type')
    op.drop_column('goals', 'template_id')

    op.execute("DROP TYPE IF EXISTS habitperiod")
    op.execute("DROP TYPE IF EXISTS habittype")
