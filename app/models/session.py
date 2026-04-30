from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models.common import Side, weight_field

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.template import TemplateExercise, WorkoutTemplate
    from app.models.user import User


class WorkoutSessionBase(SQLModel):
    user_id: int | None = Field(default=None, foreign_key="users.id")
    template_id: int | None = Field(default=None, foreign_key="workout_templates.id")
    performed_at: datetime
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class WorkoutSession(WorkoutSessionBase, table=True):
    __tablename__ = "workout_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)

    user: Optional["User"] = Relationship(back_populates="workout_sessions")
    template: Optional["WorkoutTemplate"] = Relationship(back_populates="workout_sessions")
    session_sets: List["SessionSet"] = Relationship(back_populates="session")


class SessionSet(SQLModel, table=True):
    __tablename__ = "session_sets"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int | None = Field(default=None, foreign_key="workout_sessions.id")
    exercise_id: int | None = Field(default=None, foreign_key="exercises.id")
    template_exercise_id: int | None = Field(default=None, foreign_key="template_exercises.id")
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
    pass


class WorkoutSessionRead(WorkoutSessionBase):
    id: int
