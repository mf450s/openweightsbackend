from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import JSON, Column, Numeric
from sqlmodel import Field, SQLModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    """FastAPI dependency that returns (limit, offset) from query parameters."""
    return (limit, offset)


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
