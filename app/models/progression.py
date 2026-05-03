from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.common import utcnow, weight_field


class PersonalRecord(SQLModel, table=True):
    __tablename__ = "personal_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    exercise_id: int = Field(foreign_key="exercises.id", index=True)
    pr_type: str = Field(index=True)
    value: float = weight_field()
    achieved_at: datetime = Field()
    session_set_id: int | None = Field(default=None, foreign_key="session_sets.id")
    created_at: datetime = Field(default_factory=utcnow)


class ExerciseSetRead(SQLModel):
    set_number: int
    weight_kg: float | None = None
    reps: int | None = None
    rir: int | None = None


class ExerciseSessionHistory(SQLModel):
    session_id: int
    performed_at: datetime
    sets: list[ExerciseSetRead]


class Estimated1RmPoint(SQLModel):
    performed_at: datetime
    estimated_1rm: float


class PersonalRecordEvent(SQLModel):
    pr_type: str
    value: float
    previous_value: float | None = None


class SessionSetCreateResponse(SQLModel):
    id: int
    session_id: int | None = None
    exercise_id: int | None = None
    template_exercise_id: int | None = None
    session_notes: str | None = None
    set_number: int
    side: str | None = None
    weight_kg: float | None = None
    reps: int | None = None
    rir: int | None = None
    completed: bool = True
    personal_record: PersonalRecordEvent | None = None
