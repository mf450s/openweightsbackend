from datetime import datetime
import re
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import field_validator
from sqlmodel import Field, Relationship, SQLModel

from app.models.common import TimestampedModel, json_dict_field, utcnow

if TYPE_CHECKING:
    from app.models.session import WorkoutSession
    from app.models.template import TrainingSplit


class UserBase(SQLModel):
    name: str
    default_pause_seconds: int | None = Field(default=None, ge=0)
    email: str = Field(index=True, unique=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Invalid email address.")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        return normalized


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
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class UserRead(UserBase):
    id: int
    created_at: datetime


class UserUpdate(SQLModel):
    name: str | None = None
    email: str | None = None
    default_pause_seconds: int | None = Field(default=None, ge=0)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Invalid email address.")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        return normalized


class UserPasswordUpdate(SQLModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class LoginRequest(SQLModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Invalid email address.")
        return normalized


class AuthToken(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
