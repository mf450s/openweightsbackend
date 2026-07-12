from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from pydantic import field_validator
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import Side, weight_field

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.template import TemplateExercise, WorkoutTemplate
    from app.models.user import User


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip()
    return normalized or None


def _normalize_notes(value: str | None) -> str | None:
    return _normalize_optional_text(value)


def _normalize_session_notes(value: str | None) -> str | None:
    return _normalize_optional_text(value)


class WorkoutSessionBase(SQLModel):
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    template_id: int | None = Field(default=None, foreign_key="workout_templates.id", index=True)
    performed_at: datetime = Field(index=True)
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    active_session: bool = True

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return _normalize_notes(value)


class WorkoutSession(WorkoutSessionBase, table=True):
    __tablename__ = "workout_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)

    user: Optional["User"] = Relationship(back_populates="workout_sessions")
    template: Optional["WorkoutTemplate"] = Relationship(back_populates="workout_sessions")
    session_sets: List["SessionSet"] = Relationship(back_populates="session")


class SessionSet(SQLModel, table=True):
    __tablename__ = "session_sets"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int | None = Field(default=None, foreign_key="workout_sessions.id", index=True)
    exercise_id: int | None = Field(default=None, foreign_key="exercises.id", index=True)
    template_exercise_id: int | None = Field(
        default=None, foreign_key="template_exercises.id", index=True
    )
    session_notes: str | None = None
    set_number: int
    side: Side | None = None
    weight_kg: float | None = weight_field()
    reps: int | None = None
    rir: int | None = None
    completed: bool = True

    session: Optional["WorkoutSession"] = Relationship(back_populates="session_sets")
    exercise: Optional["Exercise"] = Relationship(back_populates="session_sets")
    template_exercise: Optional["TemplateExercise"] = Relationship(back_populates="session_sets")


class WorkoutSessionCreate(WorkoutSessionBase):
    user_id: int | None = None


class WorkoutSessionRead(WorkoutSessionBase):
    id: int


class WorkoutSessionUpdate(SQLModel):
    template_id: int | None = None
    performed_at: datetime | None = None
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    active_session: bool | None = None

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return _normalize_notes(value)


class SessionSetBase(SQLModel):
    exercise_id: int | None = Field(default=None, foreign_key="exercises.id")
    template_exercise_id: int | None = Field(default=None, foreign_key="template_exercises.id")
    session_notes: str | None = None
    set_number: int
    side: Side | None = None
    weight_kg: float | None = None
    reps: int | None = None
    rir: int | None = None
    completed: bool = True

    @field_validator("session_notes")
    @classmethod
    def validate_session_notes(cls, value: str | None) -> str | None:
        return _normalize_session_notes(value)


class SessionSetCreate(SessionSetBase):
    pass


class SessionSetRead(SessionSetBase):
    id: int
    session_id: int | None = None
    personal_record: dict | None = None


class SessionSetUpdate(SQLModel):
    exercise_id: int | None = None
    template_exercise_id: int | None = None
    session_notes: str | None = None
    set_number: int | None = None
    side: Side | None = None
    weight_kg: float | None = None
    reps: int | None = None
    rir: int | None = None
    completed: bool | None = None

    @field_validator("session_notes")
    @classmethod
    def validate_session_notes(cls, value: str | None) -> str | None:
        return _normalize_session_notes(value)


class SessionSetBulkCreate(SQLModel):
    sets: list[SessionSetCreate]


class SessionSetIdsDelete(SQLModel):
    set_ids: list[int]
