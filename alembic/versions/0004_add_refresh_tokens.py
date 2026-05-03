"""add refresh_tokens table

Revision ID: 0004_add_refresh_tokens
Revises: 0003_add_composite_indexes_and_constraints
Create Date: 2026-05-03 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_refresh_tokens"
down_revision = "0003_add_composite_indexes_and_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("family_id", sa.String(), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
