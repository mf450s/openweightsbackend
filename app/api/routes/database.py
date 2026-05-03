from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, select
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.exercise import Exercise, ExerciseAlternative, MuscleGroup, MuscleRegion
from app.models.progression import PersonalRecord
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise, TrainingSplit, WorkoutTemplate
from app.models.user import RefreshToken, User, UserSettings

router = APIRouter()


class ImportSummary(BaseModel):
    imported: dict[str, int]
    replaced: bool


TABLE_MODELS: dict[str, type[SQLModel]] = {
    "muscleGroups": MuscleGroup,
    "muscleRegions": MuscleRegion,
    "users": User,
    "user_settings": UserSettings,
    "refresh_tokens": RefreshToken,
    "exercises": Exercise,
    "exercise_alternatives": ExerciseAlternative,
    "training_splits": TrainingSplit,
    "workout_templates": WorkoutTemplate,
    "template_exercises": TemplateExercise,
    "workout_sessions": WorkoutSession,
    "session_sets": SessionSet,
    "personal_records": PersonalRecord,
}

IMPORT_ORDER = list(TABLE_MODELS)
DELETE_ORDER = list(reversed(IMPORT_ORDER))


def _columns(model: type[SQLModel]) -> list[str]:
    return [column.name for column in model.__table__.columns]


def _serialize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, dict | list):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _table_to_csv(session: Session, table_name: str, model: type[SQLModel]) -> str:
    output = io.StringIO()
    fieldnames = _columns(model)
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    order_columns = list(model.__table__.primary_key.columns)
    statement = select(model)
    if order_columns:
        statement = statement.order_by(*order_columns)

    for item in session.exec(statement).all():
        writer.writerow({column: _serialize_value(getattr(item, column)) for column in fieldnames})

    return output.getvalue()


def _csv_response(csv_data: str, filename: str) -> Response:
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_bool(value: str, table_name: str, column_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid boolean for {table_name}.{column_name}.",
    )


def _deserialize_value(
    value: str,
    python_type: type,
    table_name: str,
    column_name: str,
) -> Any:
    if value == "":
        return None
    if python_type is bool:
        return _parse_bool(value, table_name, column_name)
    if python_type is int:
        return int(value)
    if python_type is float:
        return float(value)
    if python_type is Decimal:
        return Decimal(value)
    if python_type is datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if python_type in {dict, list}:
        return json.loads(value)
    return value


def _column_python_type(model: type[SQLModel], column_name: str) -> type:
    column = model.__table__.columns[column_name]
    try:
        return column.type.python_type
    except NotImplementedError:
        field = model.model_fields.get(column_name)
        if field is not None and isinstance(field.annotation, type):
            return field.annotation
        return str


def _model_primary_key(model: type[SQLModel], row: dict[str, Any]) -> Any:
    keys = [column.name for column in model.__table__.primary_key.columns]
    if not keys:
        return None
    values = [row.get(key) for key in keys]
    if any(value is None for value in values):
        return None
    if len(values) == 1:
        return values[0]
    return tuple(values)


def _import_table_csv(
    session: Session,
    table_name: str,
    csv_bytes: bytes,
) -> int:
    model = TABLE_MODELS[table_name]
    expected_columns = set(_columns(model))
    decoded = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    if reader.fieldnames is None:
        return 0

    unknown_columns = set(reader.fieldnames) - expected_columns
    if unknown_columns:
        unknown = ", ".join(sorted(unknown_columns))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown columns for {table_name}: {unknown}.",
        )

    imported = 0
    for row_number, row in enumerate(reader, start=2):
        values: dict[str, Any] = {}
        for column_name, raw_value in row.items():
            if raw_value is None:
                continue
            try:
                values[column_name] = _deserialize_value(
                    raw_value,
                    _column_python_type(model, column_name),
                    table_name,
                    column_name,
                )
            except (ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid value for {table_name}.{column_name} on row {row_number}.",
                ) from exc

        primary_key = _model_primary_key(model, values)
        existing = session.get(model, primary_key) if primary_key is not None else None
        if existing is None:
            session.add(model(**values))
        else:
            for column_name, value in values.items():
                setattr(existing, column_name, value)
            session.add(existing)
        imported += 1

    return imported


def _replace_tables(session: Session, table_names: list[str]) -> None:
    selected = set(table_names)
    for table_name in DELETE_ORDER:
        if table_name in selected:
            session.exec(delete(TABLE_MODELS[table_name]))


@router.get("/export")
def export_database(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table_name, model in TABLE_MODELS.items():
            archive.writestr(f"{table_name}.csv", _table_to_csv(session, table_name, model))
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="openweights-database-csv.zip"'},
    )


@router.get("/export/{table_name}")
def export_table(
    table_name: str,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    model = TABLE_MODELS.get(table_name)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found.")
    return _csv_response(_table_to_csv(session, table_name, model), f"{table_name}.csv")


@router.post("/import", response_model=ImportSummary)
def import_database(
    payload: bytes = Body(media_type="application/zip"),
    replace: bool = Query(default=False),
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ImportSummary:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_files = {
                name.removesuffix(".csv"): archive.read(name)
                for name in archive.namelist()
                if name.endswith(".csv") and not name.startswith("__MACOSX/")
            }
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import payload must be a ZIP of CSV files.",
        ) from exc

    unknown_tables = set(csv_files) - set(TABLE_MODELS)
    if unknown_tables:
        unknown = ", ".join(sorted(unknown_tables))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tables in import: {unknown}.",
        )

    imported: dict[str, int] = {}
    try:
        if replace:
            _replace_tables(session, list(csv_files))
        for table_name in IMPORT_ORDER:
            if table_name in csv_files:
                imported[table_name] = _import_table_csv(session, table_name, csv_files[table_name])
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import failed because the CSV data violates database constraints.",
        ) from exc

    return ImportSummary(imported=imported, replaced=replace)


@router.post("/import/{table_name}", response_model=ImportSummary)
def import_table(
    table_name: str,
    payload: bytes = Body(media_type="text/csv"),
    replace: bool = Query(default=False),
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ImportSummary:
    if table_name not in TABLE_MODELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found.")

    try:
        if replace:
            _replace_tables(session, [table_name])
        imported = _import_table_csv(session, table_name, payload)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import failed because the CSV data violates database constraints.",
        ) from exc

    return ImportSummary(imported={table_name: imported}, replaced=replace)
