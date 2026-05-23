"""add stress and activity metric types

Revision ID: 9352b3641d8d
Revises: d697755a6dc5
Create Date: 2026-05-23 21:14:24.020358

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9352b3641d8d'
down_revision: Union[str, None] = 'd697755a6dc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL does not support removing enum values, so downgrade is a no-op.
    # New values are added with IF NOT EXISTS to make this migration re-runnable.
    op.execute("ALTER TYPE metrictype ADD VALUE IF NOT EXISTS 'stress'")
    op.execute("ALTER TYPE metrictype ADD VALUE IF NOT EXISTS 'activity'")


def downgrade() -> None:
    # Cannot remove enum values in PostgreSQL without dropping and recreating the type.
    pass
