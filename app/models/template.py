from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import field_validator
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import TimestampedModel, weight_field

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.session import SessionSet, WorkoutSession
    from app.models.user import User


def _normalize_template_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 2:
        raise ValueError("Template name must be at least 2 characters long.")
    return normalized


def _normalize_split_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 2:
        raise ValueError("Split name must be at least 2 characters long.")
    return normalized


class TrainingSplitBase(SQLModel):
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_split_name(value)


class TrainingSplit(TrainingSplitBase, TimestampedModel, table=True):
    __tablename__ = "training_splits"

    id: int | None = Field(default=None, primary_key=True)

    user: "User" = Relationship(back_populates="training_splits")
    workout_templates: list["WorkoutTemplate"] = Relationship(back_populates="split")


class TrainingSplitCreate(TrainingSplitBase):
    pass


class TrainingSplitRead(TrainingSplitBase):
    id: int
    created_at: datetime


class TrainingSplitUpdate(SQLModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_split_name(value)


class WorkoutTemplateBase(SQLModel):
    split_id: int | None = Field(default=None, foreign_key="training_splits.id", index=True)
    name: str
    order_in_split: int | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_template_name(value)


class WorkoutTemplate(WorkoutTemplateBase, table=True):
    __tablename__ = "workout_templates"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)

    user: "User" = Relationship(back_populates="workout_templates")
    split: "TrainingSplit" = Relationship(back_populates="workout_templates")
    template_exercises: list["TemplateExercise"] = Relationship(back_populates="template")
    workout_sessions: list["WorkoutSession"] = Relationship(back_populates="template")


class TemplateExerciseBase(SQLModel):
    exercise_id: int | None = Field(default=None, foreign_key="exercises.id", index=True)
    sets: int | None = None
    reps: int | None = None
    rir: int | None = None
    order_in_template: int | None = None
    pause_seconds: int | None = None
    weight_kg: float | None = weight_field()


class TemplateExercise(TemplateExerciseBase, table=True):
    __tablename__ = "template_exercises"

    id: int | None = Field(default=None, primary_key=True)
    template_id: int | None = Field(default=None, foreign_key="workout_templates.id", index=True)
    updated_at: datetime | None = None

    template: "WorkoutTemplate" = Relationship(back_populates="template_exercises")
    exercise: "Exercise" = Relationship(back_populates="template_exercises")
    session_sets: list["SessionSet"] = Relationship(back_populates="template_exercise")


class TemplateExerciseCreate(TemplateExerciseBase):
    pass


class TemplateExerciseRead(TemplateExerciseBase):
    id: int
    template_id: int | None = None
    updated_at: datetime | None = None


class TemplateExerciseUpdate(SQLModel):
    exercise_id: int | None = None
    sets: int | None = None
    reps: int | None = None
    rir: int | None = None
    order_in_template: int | None = None
    pause_seconds: int | None = None
    weight_kg: float | None = None


class WorkoutTemplateCreate(WorkoutTemplateBase):
    exercises: list[TemplateExerciseCreate] = Field(default_factory=list)


class WorkoutTemplateRead(WorkoutTemplateBase):
    id: int


class WorkoutTemplateUpdate(SQLModel):
    split_id: int | None = None
    name: str | None = None
    order_in_split: int | None = None
    description: str | None = None
    exercises: list[TemplateExerciseCreate] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_template_name(value)
