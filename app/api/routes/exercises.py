from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, and_, or_, select

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_session
from app.models.exercise import (
    Exercise,
    ExerciseAlternative,
    ExerciseCreate,
    ExerciseRead,
    ExerciseUpdate,
    MuscleGroup,
    MuscleGroupCreate,
    MuscleGroupRead,
    MuscleRegion,
    MuscleRegionCreate,
    MuscleRegionRead,
)
from app.models.session import SessionSet
from app.models.template import TemplateExercise
from app.models.user import User

router = APIRouter()


def _can_access_exercise(exercise: Exercise, user: User | None) -> bool:
    if exercise.is_public:
        return True
    if user is None:
        return False
    return exercise.created_by_user_id == user.id


def _can_modify_exercise(exercise: Exercise, user: User) -> bool:
    return exercise.created_by_user_id == user.id


def _get_accessible_exercise_or_404(
    session: Session,
    exercise_id: int,
    user: User | None,
) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None or not _can_access_exercise(exercise, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found.")
    return exercise


@router.get("/muscle-groups/", response_model=list[MuscleGroupRead])
def list_muscle_groups(session: Session = Depends(get_session)) -> list[MuscleGroup]:
    statement = select(MuscleGroup).order_by(MuscleGroup.name)
    return list(session.exec(statement).all())


@router.post("/muscle-groups/", response_model=MuscleGroupRead, status_code=status.HTTP_201_CREATED)
def create_muscle_group(
    payload: MuscleGroupCreate,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MuscleGroup:
    existing = session.exec(select(MuscleGroup).where(MuscleGroup.name == payload.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A muscle group with this name already exists.",
        )

    group = MuscleGroup(name=payload.name)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@router.get("/muscle-regions/", response_model=list[MuscleRegionRead])
def list_muscle_regions(
    group_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[MuscleRegion]:
    statement = select(MuscleRegion)
    if group_id is not None:
        statement = statement.where(MuscleRegion.group_id == group_id)
    statement = statement.order_by(MuscleRegion.name)
    return list(session.exec(statement).all())


@router.post("/muscle-regions/", response_model=MuscleRegionRead, status_code=status.HTTP_201_CREATED)
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
        select(MuscleRegion).where(
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
    session.add(region)
    session.commit()
    session.refresh(region)
    return region


@router.get("/", response_model=list[ExerciseRead])
def list_exercises(
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> list[Exercise]:
    if current_user is None:
        statement = select(Exercise).where(Exercise.is_public.is_(True)).order_by(Exercise.name)
    else:
        statement = (
            select(Exercise)
            .where(
                or_(
                    Exercise.is_public.is_(True),
                    Exercise.created_by_user_id == current_user.id,
                )
            )
            .order_by(Exercise.name)
        )
    return list(session.exec(statement).all())


@router.get("/{exercise_id}", response_model=ExerciseRead)
def read_exercise(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> Exercise:
    return _get_accessible_exercise_or_404(session, exercise_id, current_user)


@router.post("/", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Exercise:
    if payload.muscle_region_id is not None and session.get(MuscleRegion, payload.muscle_region_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected muscle region does not exist.",
        )

    existing = session.exec(
        select(Exercise).where(
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
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


@router.patch("/{exercise_id}", response_model=ExerciseRead)
def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Exercise:
    exercise = _get_accessible_exercise_or_404(session, exercise_id, current_user)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        existing = session.exec(
            select(Exercise).where(
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

    if "muscle_region_id" in updates and updates["muscle_region_id"] is not None:
        if session.get(MuscleRegion, updates["muscle_region_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected muscle region does not exist.",
            )

    for field_name, value in updates.items():
        setattr(exercise, field_name, value)

    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(
    exercise_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    exercise = _get_accessible_exercise_or_404(session, exercise_id, current_user)
    if not _can_modify_exercise(exercise, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    template_usage = session.exec(
        select(TemplateExercise).where(TemplateExercise.exercise_id == exercise_id)
    ).first()
    session_usage = session.exec(select(SessionSet).where(SessionSet.exercise_id == exercise_id)).first()
    if template_usage or session_usage:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exercise is used in templates or sessions and cannot be deleted.",
        )

    alternatives = session.exec(
        select(ExerciseAlternative).where(
            or_(
                ExerciseAlternative.exercise_id == exercise_id,
                ExerciseAlternative.alternative_id == exercise_id,
            )
        )
    ).all()
    for relation in alternatives:
        session.delete(relation)

    session.delete(exercise)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{exercise_id}/alternatives", response_model=list[ExerciseRead])
def list_exercise_alternatives(
    exercise_id: int,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> list[Exercise]:
    exercise = _get_accessible_exercise_or_404(session, exercise_id, current_user)
    relation_rows = session.exec(
        select(ExerciseAlternative).where(
            or_(
                ExerciseAlternative.exercise_id == exercise.id,
                ExerciseAlternative.alternative_id == exercise.id,
            )
        )
    ).all()

    alternative_ids = {
        row.alternative_id if row.exercise_id == exercise.id else row.exercise_id for row in relation_rows
    }
    if not alternative_ids:
        return []

    alternatives = session.exec(select(Exercise).where(Exercise.id.in_(alternative_ids))).all()
    return [item for item in alternatives if _can_access_exercise(item, current_user)]


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

    exercise = _get_accessible_exercise_or_404(session, exercise_id, current_user)
    alternative = _get_accessible_exercise_or_404(session, alternative_id, current_user)
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

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{exercise_id}/alternatives/{alternative_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_exercise_alternative(
    exercise_id: int,
    alternative_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    exercise = _get_accessible_exercise_or_404(session, exercise_id, current_user)
    _get_accessible_exercise_or_404(session, alternative_id, current_user)
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

    return Response(status_code=status.HTTP_204_NO_CONTENT)
