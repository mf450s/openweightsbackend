"""add template user_id and make split user_id non-nullable

Revision ID: a43125413950
Revises: 83ed8c5c1c12
Create Date: 2026-07-12 23:51:24.424883
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = 'a43125413950'
down_revision = '83ed8c5c1c12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add user_id column to workout_templates (nullable, FK, index via model)
    # SQLite requires batch_alter_table for FK additions
    with op.batch_alter_table('workout_templates') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workout_templates_user_id', 'users', ['user_id'], ['id'])

    # 2. Make training_splits.user_id NOT NULL
    # SQLite requires batch_alter_table for ALTER COLUMN
    with op.batch_alter_table('training_splits') as batch_op:
        batch_op.alter_column('user_id', nullable=False, existing_type=sa.Integer())


def downgrade() -> None:
    # Revert: make training_splits.user_id nullable again
    with op.batch_alter_table('training_splits') as batch_op:
        batch_op.alter_column('user_id', nullable=True, existing_type=sa.Integer())

    # Revert: drop user_id column from workout_templates
    with op.batch_alter_table('workout_templates') as batch_op:
        batch_op.drop_constraint('fk_workout_templates_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')
