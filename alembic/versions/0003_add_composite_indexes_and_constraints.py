"""add composite indexes and unique constraints

Revision ID: 0003_add_composite_indexes_and_constraints
Revises: 0002_add_performance_indexes
Create Date: 2026-05-02 12:00:00
"""

from alembic import op


revision = "0003_add_composite_indexes_and_constraints"
down_revision = "0002_add_performance_indexes"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "sqlite"


def upgrade() -> None:
    op.create_index(
        "ix_exercise_alternatives_alternative_id",
        "exercise_alternatives",
        ["alternative_id"],
        unique=False,
    )
    op.create_index(
        "ix_workout_sessions_user_performed",
        "workout_sessions",
        ["user_id", "performed_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_session_sets_session_set_number",
        "session_sets",
        ["session_id", "set_number", "id"],
        unique=False,
    )
    op.create_index(
        "ix_template_exercises_template_order",
        "template_exercises",
        ["template_id", "order_in_template", "id"],
        unique=False,
    )

    if not _is_sqlite():
        op.create_unique_constraint(
            "uq_exercise_name_per_user", "exercises", ["name", "created_by_user_id"]
        )
        op.create_unique_constraint(
            "uq_muscle_region_name_per_group", "muscleRegions", ["name", "group_id"]
        )


def downgrade() -> None:
    if not _is_sqlite():
        op.drop_constraint("uq_muscle_region_name_per_group", "muscleRegions", type_="unique")
        op.drop_constraint("uq_exercise_name_per_user", "exercises", type_="unique")

    op.drop_index("ix_template_exercises_template_order", table_name="template_exercises")
    op.drop_index("ix_session_sets_session_set_number", table_name="session_sets")
    op.drop_index("ix_workout_sessions_user_performed", table_name="workout_sessions")
    op.drop_index("ix_exercise_alternatives_alternative_id", table_name="exercise_alternatives")
