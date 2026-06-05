"""Add pace_per_km to progressmetric enum.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05

"""
from typing import Union

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE progressmetric ADD VALUE IF NOT EXISTS 'pace_per_km'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — requires recreating the type.
    # Removing pace_per_km rows first to avoid constraint violation.
    op.execute("UPDATE milestones SET metric = NULL WHERE metric = 'pace_per_km'")
    op.execute("""
        ALTER TABLE milestones
            ALTER COLUMN metric TYPE varchar(50);
        DROP TYPE IF EXISTS progressmetric;
        CREATE TYPE progressmetric AS ENUM ('distance_km', 'duration_min', 'tss', 'count');
        ALTER TABLE milestones
            ALTER COLUMN metric TYPE progressmetric USING metric::progressmetric;
    """)
