"""add exercise_muscle_regions and drop obsolete muscle_region_id

The code model was refactored from a single muscle_region_id FK on exercises
to a many-to-many junction table exercise_muscle_regions. This migration
makes the database schema consistent with the code model.

Revision ID: 83ed8c5c1c12
Revises: 0005_add_active_session_to_workout_sessions
Create Date: 2026-07-12 19:35:43.250297
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = '83ed8c5c1c12'
down_revision = '0005_add_active_session_to_workout_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop obsolete index (created in 0002)
    op.drop_index("ix_exercises_muscle_region_id", table_name="exercises")

    # Batch context handles SQLite's ALTER TABLE limitations by recreating
    # the table without the dropped column + FK
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_column("muscle_region_id")

    # Create the many-to-many junction table matching the code model
    op.create_table(
        "exercise_muscle_regions",
        sa.Column("exercise_id", sa.Integer(), primary_key=True),
        sa.Column("muscle_region_id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False, server_default="primary"),
    )


def downgrade() -> None:
    op.drop_table("exercise_muscle_regions")

    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column(
                "muscle_region_id",
                sa.Integer(),
                sa.ForeignKey("muscleRegions.id"),
                nullable=True,
            ),
        )
        batch_op.create_index(
            "ix_exercises_muscle_region_id",
            ["muscle_region_id"],
            unique=False,
        )
