import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, and_, select

from app.models.common import PaginatedResponse
from app.models.exercise import (
    Exercise,
    ExerciseMuscleRegion,
    MuscleGroup,
    MuscleGroupCreate,
    MuscleGroupRead,
    MuscleGroupUpdate,
    MuscleRegion,
    MuscleRegionCreate,
    MuscleRegionInfo,
    MuscleRegionRead,
    MuscleRegionUpdate,
)
from app.services.persistence import no_content_response, save_and_refresh

_CACHE_TTL = 300
_cache: dict[str, tuple[float, Any]] = {}


def _cached_query(key: str, query_fn: Callable[[], Any]) -> Any:
    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and now - cached[0] < _CACHE_TTL:
        return cached[1]
    data = query_fn()
    _cache[key] = (now, data)
    return data


def _invalidate_cache(*keys: str) -> None:
    for key in keys:
        _cache.pop(key, None)


def muscle_region_info(session: Session, exercise_id: int) -> list[MuscleRegionInfo]:
    rows = session.exec(
        select(MuscleRegion.id, MuscleRegion.name, ExerciseMuscleRegion.target_type)
        .join(ExerciseMuscleRegion, ExerciseMuscleRegion.muscle_region_id == MuscleRegion.id)
        .where(ExerciseMuscleRegion.exercise_id == exercise_id)
        .order_by(ExerciseMuscleRegion.muscle_region_id)
    ).all()
    return [MuscleRegionInfo(id=row.id, name=row.name, target_type=row.target_type) for row in rows]


def exercise_read(exercise: Exercise, muscles: list[MuscleRegionInfo] | None = None) -> Any:
    muscles = muscles or []
    from app.models.exercise import ExerciseRead

    return ExerciseRead(
        id=exercise.id,
        name=exercise.name,
        laterality=exercise.laterality,
        created_by_user_id=exercise.created_by_user_id,
        is_public=exercise.is_public,
        execution_notes=exercise.execution_notes,
        muscle_region_ids=[muscle.id for muscle in muscles],
        muscles=muscles,
    )


def list_groups(session: Session, limit: int, offset: int) -> PaginatedResponse[MuscleGroupRead]:
    def query() -> PaginatedResponse[MuscleGroupRead]:
        base = select(MuscleGroup)
        total = session.exec(select(func.count()).select_from(base.subquery())).one()
        items = list(session.exec(base.order_by(MuscleGroup.name).offset(offset).limit(limit)).all())
        return PaginatedResponse[MuscleGroupRead](items=items, total=total, limit=limit, offset=offset)

    return _cached_query("muscle_groups", query) if offset == 0 else query()


def create_group(session: Session, payload: MuscleGroupCreate) -> MuscleGroup:
    if session.exec(select(MuscleGroup.id).where(MuscleGroup.name == payload.name)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A muscle group with this name already exists.")
    group = save_and_refresh(session, MuscleGroup(name=payload.name))
    _invalidate_cache("muscle_groups")
    return group


def update_group(session: Session, group_id: int, payload: MuscleGroupUpdate) -> MuscleGroup:
    group = session.get(MuscleGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Muscle group not found.")
    duplicate = session.exec(select(MuscleGroup.id).where(MuscleGroup.name == payload.name, MuscleGroup.id != group_id)).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A muscle group with this name already exists.")
    group.name = payload.name
    result = save_and_refresh(session, group)
    _invalidate_cache("muscle_groups")
    return result


def delete_group(session: Session, group_id: int):
    group = session.get(MuscleGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Muscle group not found.")
    count = session.exec(select(func.count()).select_from(select(MuscleRegion).where(MuscleRegion.group_id == group_id).subquery())).one()
    if count:
        raise HTTPException(status_code=409, detail=f"Cannot delete group: {count} muscle region(s) still reference it.")
    session.delete(group)
    session.commit()
    _invalidate_cache("muscle_groups")
    return no_content_response()


def list_regions(session: Session, group_id: int | None, limit: int, offset: int) -> PaginatedResponse[MuscleRegionRead]:
    def query() -> PaginatedResponse[MuscleRegionRead]:
        base = select(MuscleRegion)
        if group_id is not None:
            base = base.where(MuscleRegion.group_id == group_id)
        total = session.exec(select(func.count()).select_from(base.subquery())).one()
        items = list(session.exec(base.order_by(MuscleRegion.name).offset(offset).limit(limit)).all())
        return PaginatedResponse[MuscleRegionRead](items=items, total=total, limit=limit, offset=offset)

    key = f"muscle_regions:{group_id}"
    return _cached_query(key, query) if offset == 0 and group_id is not None else query()


def create_region(session: Session, payload: MuscleRegionCreate) -> MuscleRegion:
    if payload.group_id is not None and session.get(MuscleGroup, payload.group_id) is None:
        raise HTTPException(status_code=400, detail="Selected muscle group does not exist.")
    duplicate = session.exec(select(MuscleRegion.id).where(and_(MuscleRegion.name == payload.name, MuscleRegion.group_id == payload.group_id))).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A muscle region with this name already exists in this group.")
    result = save_and_refresh(session, MuscleRegion(name=payload.name, group_id=payload.group_id))
    _invalidate_cache(f"muscle_regions:{payload.group_id}")
    return result


def update_region(session: Session, region_id: int, payload: MuscleRegionUpdate) -> MuscleRegion:
    region = session.get(MuscleRegion, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="Muscle region not found.")
    old_key = f"muscle_regions:{region.group_id}"
    if payload.group_id is not None and session.get(MuscleGroup, payload.group_id) is None:
        raise HTTPException(status_code=400, detail="Selected muscle group does not exist.")
    duplicate = session.exec(select(MuscleRegion.id).where(and_(MuscleRegion.name == payload.name, MuscleRegion.group_id == payload.group_id, MuscleRegion.id != region_id))).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A muscle region with this name already exists in this group.")
    region.name = payload.name
    region.group_id = payload.group_id
    result = save_and_refresh(session, region)
    _invalidate_cache(old_key, f"muscle_regions:{region.group_id}")
    return result


def delete_region(session: Session, region_id: int):
    region = session.get(MuscleRegion, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="Muscle region not found.")
    count = session.exec(select(func.count()).select_from(select(ExerciseMuscleRegion).where(ExerciseMuscleRegion.muscle_region_id == region_id).subquery())).one()
    if count:
        raise HTTPException(status_code=409, detail=f"Cannot delete region: {count} exercise(s) still reference it.")
    key = f"muscle_regions:{region.group_id}"
    session.delete(region)
    session.commit()
    _invalidate_cache(key)
    return no_content_response()
