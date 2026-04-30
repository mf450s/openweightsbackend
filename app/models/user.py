from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models.common import TimestampedModel, json_dict_field, utcnow

if TYPE_CHECKING:
    from app.models.session import WorkoutSession
    from app.models.template import TrainingSplit


class UserBase(SQLModel):
    name: str
    default_pause_seconds: int | None = None
    email: str = Field(index=True, unique=True)


class User(UserBase, TimestampedModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    password_hash: str

    settings: Optional["UserSettings"] = Relationship(back_populates="user")
    training_splits: List["TrainingSplit"] = Relationship(back_populates="user")
    workout_sessions: List["WorkoutSession"] = Relationship(back_populates="user")


class UserSettings(SQLModel, table=True):
    __tablename__ = "user_settings"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    preferences: dict[str, Any] = json_dict_field()
    updated_at: datetime = Field(default_factory=utcnow)

    user: User = Relationship(back_populates="settings")


class UserCreate(UserBase):
    password_hash: str


class UserRead(UserBase):
    id: int
    created_at: datetime
