from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models.common import TimestampedModel, weight_field

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.session import SessionSet, WorkoutSession
    from app.models.user import User


class TrainingSplitBase(SQLModel):
    user_id: int | None = Field(default=None, foreign_key="users.id")
    name: str
    description: str | None = None


class TrainingSplit(TrainingSplitBase, TimestampedModel, table=True):
    __tablename__ = "training_splits"

    id: Optional[int] = Field(default=None, primary_key=True)

    user: Optional["User"] = Relationship(back_populates="training_splits")
    workout_templates: List["WorkoutTemplate"] = Relationship(back_populates="split")


class WorkoutTemplateBase(SQLModel):
    split_id: int | None = Field(default=None, foreign_key="training_splits.id")
    name: str
    order_in_split: int | None = None


class WorkoutTemplate(WorkoutTemplateBase, table=True):
    __tablename__ = "workout_templates"

    id: Optional[int] = Field(default=None, primary_key=True)

    split: Optional["TrainingSplit"] = Relationship(back_populates="workout_templates")
    template_exercises: List["TemplateExercise"] = Relationship(back_populates="template")
    workout_sessions: List["WorkoutSession"] = Relationship(back_populates="template")


class TemplateExercise(SQLModel, table=True):
    __tablename__ = "template_exercises"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int | None = Field(default=None, foreign_key="workout_templates.id")
    exercise_id: int | None = Field(default=None, foreign_key="exercises.id")
    sets: int | None = None
    reps: int | None = None
    rir: int | None = None
    order_in_template: int | None = None
    pause_seconds: int | None = None
    weight_kg: float | None = weight_field()
    updated_at: datetime | None = None

    template: Optional["WorkoutTemplate"] = Relationship(back_populates="template_exercises")
    exercise: Optional["Exercise"] = Relationship(back_populates="template_exercises")
    session_sets: List["SessionSet"] = Relationship(back_populates="template_exercise")


class WorkoutTemplateCreate(WorkoutTemplateBase):
    pass


class WorkoutTemplateRead(WorkoutTemplateBase):
    id: int
