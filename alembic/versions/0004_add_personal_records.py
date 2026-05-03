"""add personal_records table

Revision ID: 0004_add_personal_records
Revises: 0003_add_composite_indexes_and_constraints
Create Date: 2026-05-03 21:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_personal_records"
down_revision = "0003_add_composite_indexes_and_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=False, index=True),
        sa.Column("pr_type", sa.String(), nullable=False, index=True),
        sa.Column("value", sa.Numeric(6, 2), nullable=False),
        sa.Column("achieved_at", sa.DateTime(), nullable=False),
        sa.Column("session_set_id", sa.Integer(), sa.ForeignKey("session_sets.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("personal_records")
