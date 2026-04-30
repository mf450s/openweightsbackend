"""add performance indexes

Revision ID: 0002_add_performance_indexes
Revises: 0001_initial_schema
Create Date: 2026-04-30 22:40:00
"""

from alembic import op


revision = "0002_add_performance_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_muscleGroups_name", "muscleGroups", ["name"], unique=False)
    op.create_index("ix_muscleRegions_group_id", "muscleRegions", ["group_id"], unique=False)
    op.create_index("ix_muscleRegions_name", "muscleRegions", ["name"], unique=False)

    op.create_index("ix_exercises_created_by_user_id", "exercises", ["created_by_user_id"], unique=False)
    op.create_index("ix_exercises_is_public", "exercises", ["is_public"], unique=False)
    op.create_index("ix_exercises_muscle_region_id", "exercises", ["muscle_region_id"], unique=False)

    op.create_index("ix_session_sets_exercise_id", "session_sets", ["exercise_id"], unique=False)
    op.create_index("ix_session_sets_session_id", "session_sets", ["session_id"], unique=False)
    op.create_index(
        "ix_session_sets_template_exercise_id",
        "session_sets",
        ["template_exercise_id"],
        unique=False,
    )

    op.create_index("ix_template_exercises_exercise_id", "template_exercises", ["exercise_id"], unique=False)
    op.create_index("ix_template_exercises_template_id", "template_exercises", ["template_id"], unique=False)

    op.create_index("ix_training_splits_user_id", "training_splits", ["user_id"], unique=False)

    op.create_index("ix_workout_sessions_performed_at", "workout_sessions", ["performed_at"], unique=False)
    op.create_index("ix_workout_sessions_template_id", "workout_sessions", ["template_id"], unique=False)
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"], unique=False)

    op.create_index("ix_workout_templates_split_id", "workout_templates", ["split_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workout_templates_split_id", table_name="workout_templates")

    op.drop_index("ix_workout_sessions_user_id", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_template_id", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_performed_at", table_name="workout_sessions")

    op.drop_index("ix_training_splits_user_id", table_name="training_splits")

    op.drop_index("ix_template_exercises_template_id", table_name="template_exercises")
    op.drop_index("ix_template_exercises_exercise_id", table_name="template_exercises")

    op.drop_index("ix_session_sets_template_exercise_id", table_name="session_sets")
    op.drop_index("ix_session_sets_session_id", table_name="session_sets")
    op.drop_index("ix_session_sets_exercise_id", table_name="session_sets")

    op.drop_index("ix_exercises_muscle_region_id", table_name="exercises")
    op.drop_index("ix_exercises_is_public", table_name="exercises")
    op.drop_index("ix_exercises_created_by_user_id", table_name="exercises")

    op.drop_index("ix_muscleRegions_name", table_name="muscleRegions")
    op.drop_index("ix_muscleRegions_group_id", table_name="muscleRegions")
    op.drop_index("ix_muscleGroups_name", table_name="muscleGroups")
