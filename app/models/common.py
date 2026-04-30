from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Column, JSON, Numeric
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Laterality(str, Enum):
    bilateral = "bilateral"
    unilateral = "unilateral"


class Side(str, Enum):
    left = "left"
    right = "right"
    bilateral = "bilateral"


class TimestampedModel(SQLModel):
    created_at: datetime = Field(default_factory=utcnow, nullable=False)


def json_dict_field() -> Any:
    return Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


def weight_field() -> Any:
    return Field(default=None, sa_column=Column(Numeric(6, 2), nullable=True))
