import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, and_, delete, or_, select

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_session
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
    MuscleRegion,
    MuscleRegionCreate,
    MuscleRegionRead,
)
from app.models.progression import Estimated1RmPoint, ExerciseSessionHistory, ExerciseSetRead
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise
from app.models.user import User
from app.services.exercise_access import can_access_exercise, get_accessible_exercise_or_404
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


def _get_muscle_region_ids(session: Session, exercise_id: int) -> list[int]:
    rows = session.exec(
        select(ExerciseMuscleRegion.muscle_region_id)
        .where(ExerciseMuscleRegion.exercise_id == exercise_id)
        .order_by(ExerciseMuscleRegion.muscle_region_id)
    ).all()
    return list(rows)


def _exercise_to_read(
    exercise: Exercise, muscle_region_ids: list[int] | None = None
) -> ExerciseRead:
    return ExerciseRead(
        id=exercise.id,
        name=exercise.name,
        laterality=exercise.laterality,
        created_by_user_id=exercise.created_by_user_id,
        is_public=exercise.is_public,
        execution_notes=exercise.execution_notes,
        muscle_region_ids=muscle_region_ids or [],
    )


@router.get("/muscle-groups/", response_model=list[MuscleGroupRead])
def list_muscle_groups(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[MuscleGroup]:
    def _query():
        statement = select(MuscleGroup).order_by(MuscleGroup.name).offset(offset).limit(limit)
        return list(session.exec(statement).all())

    if offset == 0:
        return _cached_query("muscle_groups", _CACHE_TTL, _query)
    return _query()


@router.post("/muscle-groups/", response_model=MuscleGroupRead, status_code=status.HTTP_201_CREATED)
def create_muscle_group(
    payload: MuscleGroupCreate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleGroup:
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


@router.get("/muscle-regions/", response_model=list[MuscleRegionRead])
def list_muscle_regions(
    group_id: int | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[MuscleRegion]:
    def _query():
        statement = select(MuscleRegion)
        if group_id is not None:
            statement = statement.where(MuscleRegion.group_id == group_id)
        statement = statement.order_by(MuscleRegion.name).offset(offset).limit(limit)
        return list(session.exec(statement).all())

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


@router.get("/", response_model=list[ExerciseRead])
def list_exercises(
    current_user: User | None = Depends(get_optional_current_user),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[Exercise]:
    if current_user is None:
        statement = (
            select(Exercise)
            .where(Exercise.is_public.is_(True))
            .order_by(Exercise.name)
            .offset(offset)
            .limit(limit)
        )
    else:
        statement = (
            select(Exercise)
            .where(Exercise.is_public.is_(True))
            .union(select(Exercise).where(Exercise.created_by_user_id == current_user.id))
            .order_by(Exercise.name)
            .offset(offset)
            .limit(limit)
        )
    exercises = list(session.exec(statement).all())
    return [
        _exercise_to_read(e, _get_muscle_region_ids(session, e.id))
        for e in exercises
    ]


@router.get("/{exercise_id}", response_model=ExerciseRead)
def read_exercise(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    exercise = get_accessible_exercise_or_404(
        session=session,
        exercise_id=exercise_id,
        user_id=current_user.id if current_user is not None else None,
    )
    return _exercise_to_read(exercise, _get_muscle_region_ids(session, exercise.id))


@router.post("/", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    for rid in payload.muscle_region_ids:
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
    for rid in payload.muscle_region_ids:
        session.add(ExerciseMuscleRegion(exercise_id=exercise.id, muscle_region_id=rid))
    session.commit()
    session.refresh(exercise)
    return _exercise_to_read(exercise, payload.muscle_region_ids)


@router.patch("/{exercise_id}", response_model=ExerciseRead)
def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    exercise = get_accessible_exercise_or_404(session, exercise_id, current_user.id)
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
    if muscle_region_ids is not None:
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
    final_ids = _get_muscle_region_ids(session, exercise.id)
    return _exercise_to_read(exercise, final_ids)


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    exercise = get_accessible_exercise_or_404(session, exercise_id, current_user.id)
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
    session: Session = Depends(get_session),
) -> list[dict]:
    get_accessible_exercise_or_404(session, exercise_id, current_user.id)

    rows = session.exec(
        select(SessionSet, WorkoutSession)
        .join(WorkoutSession)
        .where(
            SessionSet.exercise_id == exercise_id,
            WorkoutSession.user_id == current_user.id,
            SessionSet.completed,
        )
        .order_by(WorkoutSession.performed_at, WorkoutSession.id, SessionSet.set_number)
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


@router.get("/{exercise_id}/1rm", response_model=list[Estimated1RmPoint])
def exercise_1rm_history(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    get_accessible_exercise_or_404(session, exercise_id, current_user.id)

    rows = session.exec(
        select(SessionSet)
        .join(WorkoutSession)
        .where(
            SessionSet.exercise_id == exercise_id,
            WorkoutSession.user_id == current_user.id,
            SessionSet.completed,
        )
        .order_by(WorkoutSession.performed_at, WorkoutSession.id, SessionSet.set_number)
    ).all()

    session_sets: dict[int, list[SessionSet]] = {}
    session_dates: dict[int, datetime] = {}
    for session_set in rows:
        sid = session_set.session_id
        session_sets.setdefault(sid, []).append(session_set)
        if sid not in session_dates:
            session_dates[sid] = session_set.session.performed_at

    result = []
    for sid in sorted(session_sets.keys(), key=lambda sid: session_dates[sid]):
        best = get_best_1rm_for_session(session_sets[sid])
        if best is not None:
            result.append(Estimated1RmPoint(performed_at=session_dates[sid], estimated_1rm=best))

    return result


@router.get("/{exercise_id}/alternatives", response_model=list[ExerciseRead])
def list_exercise_alternatives(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> list[Exercise]:
    exercise = get_accessible_exercise_or_404(
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

    exercise = get_accessible_exercise_or_404(session, exercise_id, current_user.id)
    alternative = get_accessible_exercise_or_404(session, alternative_id, current_user.id)
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
    exercise = get_accessible_exercise_or_404(session, exercise_id, current_user.id)
    get_accessible_exercise_or_404(session, alternative_id, current_user.id)
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
