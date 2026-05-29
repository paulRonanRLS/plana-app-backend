"""add milestone progress tracking fields

Revision ID: f0a1b2c3d4e5
Revises: e9f2a4b6c8d0
Create Date: 2026-05-28 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e9f2a4b6c8d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE progresstype AS ENUM ('cumulative', 'single_effort'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE progressmetric AS ENUM ('distance_km', 'duration_min', 'tss', 'count'); EXCEPTION WHEN duplicate_object THEN null; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE progressperiod AS ENUM ('week', 'month', 'lifetime'); EXCEPTION WHEN duplicate_object THEN null; END $$")

    op.add_column('milestones', sa.Column('activity_type', sa.String(50), nullable=True))
    op.add_column('milestones', sa.Column('progress_type', sa.Enum('cumulative', 'single_effort', name='progresstype', create_type=False), nullable=True))
    op.add_column('milestones', sa.Column('metric', sa.Enum('distance_km', 'duration_min', 'tss', 'count', name='progressmetric', create_type=False), nullable=True))
    op.add_column('milestones', sa.Column('target_value', sa.Float(), nullable=True))
    op.add_column('milestones', sa.Column('period', sa.Enum('week', 'month', 'lifetime', name='progressperiod', create_type=False), nullable=True))
    op.add_column('milestones', sa.Column('current_value', sa.Float(), nullable=False, server_default='0.0'))


def downgrade() -> None:
    op.drop_column('milestones', 'current_value')
    op.drop_column('milestones', 'period')
    op.drop_column('milestones', 'target_value')
    op.drop_column('milestones', 'metric')
    op.drop_column('milestones', 'progress_type')
    op.drop_column('milestones', 'activity_type')

    op.execute("DROP TYPE IF EXISTS progressperiod")
    op.execute("DROP TYPE IF EXISTS progressmetric")
    op.execute("DROP TYPE IF EXISTS progresstype")
