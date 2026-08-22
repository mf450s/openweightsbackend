import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, and_, delete, or_, select

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_session
from app.models.common import PaginatedResponse
from app.models.exercise import (
    Exercise,
    ExerciseAlternative,
    ExerciseCreate,
    ExerciseMuscleRegion,
    ExerciseRead,
    ExerciseUpdate,
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
from app.models.progression import (
    ExerciseSessionHistory,
    ExerciseSetRead,
    OneRmHistoryPoint,
)
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise
from app.models.user import User
from app.services.exercise_access import can_access_exercise, get_accessible_exercise_or_403
from app.services.exercise_taxonomy import (
    create_group,
    create_region,
    delete_group,
    delete_region,
    exercise_read,
    list_groups,
    list_regions,
    muscle_region_info,
    update_group,
    update_region,
)
from app.services.persistence import no_content_response, save_and_refresh
from app.services.progression_service import get_best_1rm_for_session

router = APIRouter()


_CACHE_TTL = 300
_cache: dict[str, tuple[float, list]] = {}


def _cached_query(key: str, ttl: int, query_fn):
    now = time.monotonic()
    if key in _cache:
        timestamp, data = _cache[key]
        if now - timestamp < ttl:
            return data
    data = query_fn()
    _cache[key] = (now, data)
    return data


def _invalidate_cache(*keys: str) -> None:
    for key in keys:
        _cache.pop(key, None)


def _can_modify_exercise(exercise: Exercise, user: User) -> bool:
    return exercise.created_by_user_id == user.id


def _get_muscle_region_info(session: Session, exercise_id: int) -> list[MuscleRegionInfo]:
    return muscle_region_info(session, exercise_id)
    rows = session.exec(
        select(MuscleRegion.id, MuscleRegion.name, ExerciseMuscleRegion.target_type)
        .join(ExerciseMuscleRegion, ExerciseMuscleRegion.muscle_region_id == MuscleRegion.id)
        .where(ExerciseMuscleRegion.exercise_id == exercise_id)
        .order_by(ExerciseMuscleRegion.muscle_region_id)
    ).all()
    return [MuscleRegionInfo(id=row.id, name=row.name, target_type=row.target_type) for row in rows]


def _exercise_to_read(
    exercise: Exercise, muscles: list[MuscleRegionInfo] | None = None
) -> ExerciseRead:
    return exercise_read(exercise, muscles)
    muscles = muscles or []
    return ExerciseRead(
        id=exercise.id,
        name=exercise.name,
        laterality=exercise.laterality,
        created_by_user_id=exercise.created_by_user_id,
        is_public=exercise.is_public,
        execution_notes=exercise.execution_notes,
        muscle_region_ids=[m.id for m in muscles],
        muscles=muscles,
    )


@router.get("/muscle-groups/", response_model=PaginatedResponse)
def list_muscle_groups(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[MuscleGroupRead]:
    return list_groups(session, limit, offset)
    def _query():
        base = select(MuscleGroup)
        total = session.exec(select(func.count()).select_from(base.subquery())).one()
        items = list(
            session.exec(base.order_by(MuscleGroup.name).offset(offset).limit(limit)).all()
        )
        return PaginatedResponse[MuscleGroupRead](
            items=items, total=total, limit=limit, offset=offset
        )

    if offset == 0:
        return _cached_query("muscle_groups", _CACHE_TTL, _query)
    return _query()


@router.post("/muscle-groups/", response_model=MuscleGroupRead, status_code=status.HTTP_201_CREATED)
def create_muscle_group(
    payload: MuscleGroupCreate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleGroup:
    return create_group(session, payload)
    existing = session.exec(select(MuscleGroup.id).where(MuscleGroup.name == payload.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A muscle group with this name already exists.",
        )

    group = MuscleGroup(name=payload.name)
    result = save_and_refresh(session, group)
    _invalidate_cache("muscle_groups")
    return result


@router.patch("/muscle-groups/{group_id}", response_model=MuscleGroupRead)
def update_muscle_group(
    group_id: int,
    payload: MuscleGroupUpdate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleGroup:
    return update_group(session, group_id, payload)
    group = session.get(MuscleGroup, group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Muscle group not found.",
        )

    existing = session.exec(
        select(MuscleGroup.id).where(
            MuscleGroup.name == payload.name, MuscleGroup.id != group_id
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A muscle group with this name already exists.",
        )

    group.name = payload.name
    result = save_and_refresh(session, group)
    _invalidate_cache("muscle_groups")
    return result


@router.delete("/muscle-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_muscle_group(
    group_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    return delete_group(session, group_id)
    group = session.get(MuscleGroup, group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Muscle group not found.",
        )

    # Check if any regions reference this group
    region_count = session.exec(
        select(func.count()).select_from(
            select(MuscleRegion).where(MuscleRegion.group_id == group_id).subquery()
        )
    ).one()
    if region_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete group: {region_count} muscle region(s) still reference it.",
        )

    session.delete(group)
    session.commit()
    _invalidate_cache("muscle_groups")
    return no_content_response()


@router.get("/muscle-regions/", response_model=PaginatedResponse)
def list_muscle_regions(
    group_id: int | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[MuscleRegionRead]:
    return list_regions(session, group_id, limit, offset)
    def _query():
        base = select(MuscleRegion)
        if group_id is not None:
            base = base.where(MuscleRegion.group_id == group_id)
        total = session.exec(select(func.count()).select_from(base.subquery())).one()
        items = list(session.exec(base.order_by(MuscleRegion.name).offset(offset).limit(limit)).all())
        return PaginatedResponse[MuscleRegionRead](
            items=items, total=total, limit=limit, offset=offset
        )

    cache_key = f"muscle_regions:{group_id}"
    if offset == 0 and group_id is not None:
        return _cached_query(cache_key, _CACHE_TTL, _query)
    return _query()


@router.post(
    "/muscle-regions/", response_model=MuscleRegionRead, status_code=status.HTTP_201_CREATED
)
def create_muscle_region(
    payload: MuscleRegionCreate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleRegion:
    return create_region(session, payload)
    if payload.group_id is not None and session.get(MuscleGroup, payload.group_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected muscle group does not exist.",
        )

    existing = session.exec(
        select(MuscleRegion.id).where(
            and_(
                MuscleRegion.name == payload.name,
                MuscleRegion.group_id == payload.group_id,
            )
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A muscle region with this name already exists in this group.",
        )

    region = MuscleRegion(name=payload.name, group_id=payload.group_id)
    result = save_and_refresh(session, region)
    _invalidate_cache(f"muscle_regions:{payload.group_id}")
    return result


@router.patch("/muscle-regions/{region_id}", response_model=MuscleRegionRead)
def update_muscle_region(
    region_id: int,
    payload: MuscleRegionUpdate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleRegion:
    return update_region(session, region_id, payload)
    region = session.get(MuscleRegion, region_id)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Muscle region not found.",
        )

    if payload.group_id is not None and session.get(MuscleGroup, payload.group_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected muscle group does not exist.",
        )

    existing = session.exec(
        select(MuscleRegion.id).where(
            and_(
                MuscleRegion.name == payload.name,
                MuscleRegion.group_id == payload.group_id,
                MuscleRegion.id != region_id,
            )
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A muscle region with this name already exists in this group.",
        )

    region.name = payload.name
    region.group_id = payload.group_id
    result = save_and_refresh(session, region)
    _invalidate_cache(f"muscle_regions:{payload.group_id}", f"muscle_regions:{region.group_id}")
    return result


@router.delete("/muscle-regions/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_muscle_region(
    region_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    return delete_region(session, region_id)
    region = session.get(MuscleRegion, region_id)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Muscle region not found.",
        )

    # Check if any exercises reference this region
    exercise_count = session.exec(
        select(func.count()).select_from(
            select(ExerciseMuscleRegion).where(
                ExerciseMuscleRegion.muscle_region_id == region_id
            ).subquery()
        )
    ).one()
    if exercise_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete region: {exercise_count} exercise(s) still reference it.",
        )

    session.delete(region)
    session.commit()
    _invalidate_cache(f"muscle_regions:{region.group_id}")
    return no_content_response()


@router.get("/", response_model=PaginatedResponse)
def list_exercises(
    current_user: User | None = Depends(get_optional_current_user),
    search: str | None = None,
    muscle_region_id: int | None = None,
    muscle_group_id: int | None = None,
    laterality: str | None = None,
    created_by: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[ExerciseRead]:
    if current_user is None:
        base = select(Exercise).where(Exercise.is_public.is_(True))
    else:
        if created_by == "me":
            base = select(Exercise).where(Exercise.created_by_user_id == current_user.id)
        elif created_by == "public":
            base = select(Exercise).where(Exercise.is_public.is_(True))
        elif created_by == "all":
            base = select(Exercise).where(
                or_(
                    Exercise.is_public.is_(True),
                    Exercise.created_by_user_id == current_user.id,
                )
            )
        else:
            base = select(Exercise).where(
                or_(
                    Exercise.is_public.is_(True),
                    Exercise.created_by_user_id == current_user.id,
                )
            )
    if search is not None:
        base = base.where(Exercise.name.ilike(f"%{search}%"))
    if muscle_region_id is not None:
        base = base.where(
            Exercise.id.in_(
                select(ExerciseMuscleRegion.exercise_id).where(
                    ExerciseMuscleRegion.muscle_region_id == muscle_region_id
                )
            )
        )
    if muscle_group_id is not None:
        base = base.where(
            Exercise.id.in_(
                select(ExerciseMuscleRegion.exercise_id)
                .join(MuscleRegion, ExerciseMuscleRegion.muscle_region_id == MuscleRegion.id)
                .where(MuscleRegion.group_id == muscle_group_id)
            )
        )
    if laterality is not None:
        base = base.where(Exercise.laterality == laterality)

    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    statement = base.order_by(Exercise.name).offset(offset).limit(limit)
    exercises = list(session.exec(statement).all())
    items = [
        _exercise_to_read(e, _get_muscle_region_info(session, e.id))
        for e in exercises
    ]
    return PaginatedResponse[ExerciseRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{exercise_id}", response_model=ExerciseRead)
def read_exercise(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    exercise = get_accessible_exercise_or_403(
        session=session,
        exercise_id=exercise_id,
        user_id=current_user.id if current_user is not None else None,
    )
    return _exercise_to_read(exercise, _get_muscle_region_info(session, exercise.id))


@router.post("/", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    muscle_region_ids = payload.muscle_region_ids
    if not muscle_region_ids and payload.muscle_region_id is not None:
        muscle_region_ids = [payload.muscle_region_id]
    muscle_region_ids = list(dict.fromkeys(muscle_region_ids))

    for rid in muscle_region_ids:
        if session.get(MuscleRegion, rid) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Muscle region {rid} does not exist.",
            )

    existing = session.exec(
        select(Exercise.id).where(
            and_(
                Exercise.name == payload.name,
                Exercise.created_by_user_id == current_user.id,
            )
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an exercise with this name.",
        )

    exercise = Exercise.model_validate(payload)
    exercise.created_by_user_id = current_user.id
    exercise = save_and_refresh(session, exercise)
    for rid in muscle_region_ids:
        session.add(ExerciseMuscleRegion(exercise_id=exercise.id, muscle_region_id=rid))
    session.commit()
    session.refresh(exercise)
    return _exercise_to_read(exercise, _get_muscle_region_info(session, exercise.id))


@router.patch("/{exercise_id}", response_model=ExerciseRead)
def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    exercise = get_accessible_exercise_or_403(session, exercise_id, current_user.id)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        existing = session.exec(
            select(Exercise.id).where(
                and_(
                    Exercise.name == updates["name"],
                    Exercise.created_by_user_id == current_user.id,
                    Exercise.id != exercise_id,
                )
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an exercise with this name.",
            )

    muscle_region_ids = updates.pop("muscle_region_ids", None)
    if muscle_region_ids is None:
        muscle_region_id = updates.pop("muscle_region_id", None)
        if muscle_region_id is not None:
            muscle_region_ids = [muscle_region_id]
    if muscle_region_ids is not None:
        muscle_region_ids = list(dict.fromkeys(muscle_region_ids))
        for rid in muscle_region_ids:
            if session.get(MuscleRegion, rid) is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Muscle region {rid} does not exist.",
                )
        session.exec(
            delete(ExerciseMuscleRegion).where(ExerciseMuscleRegion.exercise_id == exercise_id)
        )
        for rid in muscle_region_ids:
            session.add(ExerciseMuscleRegion(exercise_id=exercise_id, muscle_region_id=rid))

    exercise.sqlmodel_update(updates)
    exercise = save_and_refresh(session, exercise)
    return _exercise_to_read(exercise, _get_muscle_region_info(session, exercise.id))


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    exercise = get_accessible_exercise_or_403(session, exercise_id, current_user.id)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    usage = (
        session.exec(
            select(TemplateExercise.id)
            .where(TemplateExercise.exercise_id == exercise_id)
            .union(select(SessionSet.id).where(SessionSet.exercise_id == exercise_id))
        )
        .scalars()
        .first()
    )
    if usage is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exercise is used in templates or sessions and cannot be deleted.",
        )

    session.exec(
        delete(ExerciseAlternative).where(
            or_(
                ExerciseAlternative.exercise_id == exercise_id,
                ExerciseAlternative.alternative_id == exercise_id,
            )
        )
    )

    session.delete(exercise)
    session.commit()
    return no_content_response()


@router.get("/{exercise_id}/history", response_model=list[ExerciseSessionHistory])
def exercise_history(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict]:
    get_accessible_exercise_or_403(session, exercise_id, current_user.id)

    rows = session.exec(
        select(SessionSet, WorkoutSession)
        .join(WorkoutSession)
        .where(
            SessionSet.exercise_id == exercise_id,
            WorkoutSession.user_id == current_user.id,
            SessionSet.completed,
        )
        .order_by(WorkoutSession.performed_at.desc(), WorkoutSession.id.desc(), SessionSet.set_number)
        .offset(offset)
        .limit(limit)
    ).all()

    grouped: dict[int, dict] = {}
    for session_set, workout_session in rows:
        sid = workout_session.id
        if sid not in grouped:
            grouped[sid] = {
                "session_id": sid,
                "performed_at": workout_session.performed_at,
                "sets": [],
            }
        grouped[sid]["sets"].append(
            ExerciseSetRead(
                set_number=session_set.set_number,
                weight_kg=(
                    float(session_set.weight_kg) if session_set.weight_kg is not None else None
                ),
                reps=session_set.reps,
                rir=session_set.rir,
            )
        )

    return list(grouped.values())


@router.get("/{exercise_id}/1rm-history", response_model=list[OneRmHistoryPoint])
def exercise_1rm_history(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict]:
    get_accessible_exercise_or_403(session, exercise_id, current_user.id)

    # Get unique session ids ordered by performed_at DESC.
    # Use a subquery + IN instead of JOIN + DISTINCT to avoid SQLite's
    # limitation where DISTINCT ignores ORDER BY on unselected columns.
    subq = select(SessionSet.session_id).where(
        SessionSet.exercise_id == exercise_id,
        SessionSet.completed,
    ).subquery()

    session_id_rows = session.exec(
        select(WorkoutSession.id)
        .where(
            WorkoutSession.id.in_(select(subq.c.session_id)),
            WorkoutSession.user_id == current_user.id,
        )
        .order_by(WorkoutSession.performed_at.desc(), WorkoutSession.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    if not session_id_rows:
        return []

    session_ids = list(session_id_rows)

    rows = session.exec(
        select(SessionSet)
        .where(
            SessionSet.exercise_id == exercise_id,
            SessionSet.session_id.in_(session_ids),
            SessionSet.completed,
        )
        .order_by(SessionSet.session_id, SessionSet.set_number)
    ).all()

    session_sets: dict[int, list[SessionSet]] = {}
    session_dates: dict[int, datetime] = {}
    for session_set in rows:
        sid = session_set.session_id
        session_sets.setdefault(sid, []).append(session_set)
        if sid not in session_dates:
            session_dates[sid] = session_set.session.performed_at

    result = []
    for sid in session_ids:
        if sid in session_sets:
            best = get_best_1rm_for_session(session_sets[sid])
            if best is not None:
                result.append(
                    OneRmHistoryPoint(
                        session_id=sid,
                        performed_at=session_dates[sid],
                        estimated_1rm=best,
                    )
                )

    return result


@router.get("/{exercise_id}/alternatives", response_model=list[ExerciseRead])
def list_exercise_alternatives(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> list[Exercise]:
    exercise = get_accessible_exercise_or_403(
        session=session,
        exercise_id=exercise_id,
        user_id=current_user.id if current_user is not None else None,
    )
    alternative_ids = (
        session.exec(
            select(ExerciseAlternative.alternative_id)
            .where(ExerciseAlternative.exercise_id == exercise.id)
            .union(
                select(ExerciseAlternative.exercise_id).where(
                    ExerciseAlternative.alternative_id == exercise.id
                )
            )
        )
        .scalars()
        .all()
    )
    if not alternative_ids:
        return []

    alternatives = session.exec(
        select(Exercise)
        .where(Exercise.id.in_(alternative_ids))
        .order_by(Exercise.name, Exercise.id)
    ).all()
    current_user_id = current_user.id if current_user is not None else None
    return [item for item in alternatives if can_access_exercise(item, current_user_id)]


@router.post("/{exercise_id}/alternatives/{alternative_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_exercise_alternative(
    exercise_id: int,
    alternative_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    if exercise_id == alternative_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An exercise cannot be an alternative to itself.",
        )

    exercise = get_accessible_exercise_or_403(session, exercise_id, current_user.id)
    alternative = get_accessible_exercise_or_403(session, alternative_id, current_user.id)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    left_id, right_id = sorted((exercise.id, alternative.id))
    existing = session.exec(
        select(ExerciseAlternative).where(
            and_(
                ExerciseAlternative.exercise_id == left_id,
                ExerciseAlternative.alternative_id == right_id,
            )
        )
    ).first()
    if existing is None:
        session.add(ExerciseAlternative(exercise_id=left_id, alternative_id=right_id))
        session.commit()

    return no_content_response()


@router.delete(
    "/{exercise_id}/alternatives/{alternative_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_exercise_alternative(
    exercise_id: int,
    alternative_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    exercise = get_accessible_exercise_or_403(session, exercise_id, current_user.id)
    get_accessible_exercise_or_403(session, alternative_id, current_user.id)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    left_id, right_id = sorted((exercise_id, alternative_id))
    relation = session.exec(
        select(ExerciseAlternative).where(
            and_(
                ExerciseAlternative.exercise_id == left_id,
                ExerciseAlternative.alternative_id == right_id,
            )
        )
    ).first()
    if relation is not None:
        session.delete(relation)
        session.commit()

    return no_content_response()
