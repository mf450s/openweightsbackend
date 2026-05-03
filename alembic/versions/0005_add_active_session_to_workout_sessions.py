"""add active_session to workout_sessions

Revision ID: 0005_add_active_session_to_workout_sessions
Revises: 0004_add_refresh_tokens, 0004_add_personal_records
Create Date: 2026-05-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_active_session_to_workout_sessions"
down_revision = ("0004_add_refresh_tokens", "0004_add_personal_records")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workout_sessions",
        sa.Column("active_session", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("workout_sessions", "active_session")
