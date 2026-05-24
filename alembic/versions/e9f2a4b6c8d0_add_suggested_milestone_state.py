"""add suggested value to milestonestate enum

Revision ID: e9f2a4b6c8d0
Revises: c3d5e7f9b1a2
Create Date: 2026-05-24 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e9f2a4b6c8d0'
down_revision: Union[str, None] = 'c3d5e7f9b1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE milestonestate ADD VALUE IF NOT EXISTS 'suggested' BEFORE 'pending'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without a full type rebuild.
    pass
