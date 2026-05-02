from typing import Any, List, Optional, TYPE_CHECKING

from pydantic import field_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import Laterality

if TYPE_CHECKING:
    from app.models.session import SessionSet
    from app.models.template import TemplateExercise


class MuscleGroup(SQLModel, table=True):
    __tablename__ = "muscleGroups"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    regions: List["MuscleRegion"] = Relationship(back_populates="group")


class MuscleRegion(SQLModel, table=True):
    __tablename__ = "muscleRegions"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    group_id: int | None = Field(default=None, foreign_key="muscleGroups.id", index=True)

    group: Optional["MuscleGroup"] = Relationship(back_populates="regions")
    exercises: List["Exercise"] = Relationship(back_populates="muscle_region")

    __table_args__: tuple = (
        UniqueConstraint("name", "group_id", name="uq_muscle_region_name_per_group"),
    )


class ExerciseBase(SQLModel):
    name: str = Field(index=True)
    muscle_region_id: int | None = Field(default=None, foreign_key="muscleRegions.id", index=True)
    laterality: Laterality = Field(default=Laterality.bilateral)
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    is_public: bool = Field(default=False, index=True)
    execution_notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Exercise name must be at least 2 characters long.")
        return normalized

    @field_validator("execution_notes")
    @classmethod
    def validate_execution_notes(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class Exercise(ExerciseBase, table=True):
    __tablename__ = "exercises"

    id: Optional[int] = Field(default=None, primary_key=True)

    muscle_region: Optional["MuscleRegion"] = Relationship(back_populates="exercises")
    template_exercises: List["TemplateExercise"] = Relationship(back_populates="exercise")
    session_sets: List["SessionSet"] = Relationship(back_populates="exercise")

    __table_args__: tuple = (
        UniqueConstraint("name", "created_by_user_id", name="uq_exercise_name_per_user"),
    )


class ExerciseAlternative(SQLModel, table=True):
    __tablename__ = "exercise_alternatives"

    exercise_id: int = Field(foreign_key="exercises.id", primary_key=True)
    alternative_id: int = Field(foreign_key="exercises.id", primary_key=True, index=True)


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseRead(ExerciseBase):
    id: int


class ExerciseUpdate(SQLModel):
    name: str | None = None
    muscle_region_id: int | None = None
    laterality: Laterality | None = None
    is_public: bool | None = None
    execution_notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Exercise name must be at least 2 characters long.")
        return normalized

    @field_validator("execution_notes")
    @classmethod
    def validate_execution_notes(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class MuscleGroupCreate(SQLModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Muscle group name must be at least 2 characters long.")
        return normalized


class MuscleGroupRead(SQLModel):
    id: int
    name: str


class MuscleRegionCreate(SQLModel):
    name: str
    group_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Muscle region name must be at least 2 characters long.")
        return normalized


class MuscleRegionRead(SQLModel):
    id: int
    name: str
    group_id: int | None = None
