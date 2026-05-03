"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-30 21:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


laterality_enum = sa.Enum("bilateral", "unilateral", name="laterality")
side_enum = sa.Enum("left", "right", "bilateral", name="side")


def upgrade() -> None:
    op.create_table(
        "muscleGroups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "muscleRegions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("muscleGroups.id"), nullable=True),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("preferences", sqlite.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "training_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("muscle_region_id", sa.Integer(), sa.ForeignKey("muscleRegions.id"), nullable=True),
        sa.Column("laterality", laterality_enum, nullable=False, server_default="bilateral"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_exercises_name", "exercises", ["name"], unique=False)
    op.create_table(
        "exercise_alternatives",
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), primary_key=True),
        sa.Column("alternative_id", sa.Integer(), sa.ForeignKey("exercises.id"), primary_key=True),
    )
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("split_id", sa.Integer(), sa.ForeignKey("training_splits.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order_in_split", sa.Integer(), nullable=True),
    )
    op.create_table(
        "template_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("workout_templates.id"), nullable=True),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=True),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("rir", sa.Integer(), nullable=True),
        sa.Column("order_in_template", sa.Integer(), nullable=True),
        sa.Column("pause_seconds", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("workout_templates.id"), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "session_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("workout_sessions.id"), nullable=True),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id"), nullable=True),
        sa.Column(
            "template_exercise_id",
            sa.Integer(),
            sa.ForeignKey("template_exercises.id"),
            nullable=True,
        ),
        sa.Column("session_notes", sa.Text(), nullable=True),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("side", side_enum, nullable=True),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("rir", sa.Integer(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("session_sets")
    op.drop_table("workout_sessions")
    op.drop_table("template_exercises")
    op.drop_table("workout_templates")
    op.drop_table("exercise_alternatives")
    op.drop_index("ix_exercises_name", table_name="exercises")
    op.drop_table("exercises")
    op.drop_table("training_splits")
    op.drop_table("user_settings")
    op.drop_table("muscleRegions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("muscleGroups")
    laterality_enum.drop(op.get_bind(), checkfirst=False)
    side_enum.drop(op.get_bind(), checkfirst=False)
