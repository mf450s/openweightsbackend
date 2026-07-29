"""Add description column to workout_templates

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2025-03-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('workout_templates', sa.Column('description', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('workout_templates', 'description')
