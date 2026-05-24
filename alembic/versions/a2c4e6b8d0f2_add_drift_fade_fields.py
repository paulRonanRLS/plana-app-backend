"""add drift and fade detection fields to goals

Revision ID: a2c4e6b8d0f2
Revises: 9352b3641d8d
Create Date: 2026-05-24 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2c4e6b8d0f2'
down_revision: Union[str, None] = '9352b3641d8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    goaltype_enum = sa.Enum('perpetual', 'achievement', name='goaltype')
    goaltype_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('goals', sa.Column('goal_type', sa.Enum('perpetual', 'achievement', name='goaltype'), nullable=True))
    op.add_column('goals', sa.Column('target_metric_type', sa.String(50), nullable=True))
    op.add_column('goals', sa.Column('target_min', sa.Float(), nullable=True))
    op.add_column('goals', sa.Column('target_max', sa.Float(), nullable=True))
    op.add_column('goals', sa.Column('is_recovering', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('goals', 'is_recovering')
    op.drop_column('goals', 'target_max')
    op.drop_column('goals', 'target_min')
    op.drop_column('goals', 'target_metric_type')
    op.drop_column('goals', 'goal_type')
    sa.Enum(name='goaltype').drop(op.get_bind(), checkfirst=True)
