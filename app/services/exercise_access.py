from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.exercise import Exercise


def can_access_exercise(exercise: Exercise, user_id: int | None) -> bool:
    if exercise.is_public:
        return True
    if user_id is None:
        return False
    return exercise.created_by_user_id == user_id


def get_accessible_exercise_or_404(
    session: Session,
    exercise_id: int,
    user_id: int | None,
) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None or not can_access_exercise(exercise, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found.")
    return exercise


def get_accessible_exercise_or_403(
    session: Session,
    exercise_id: int,
    user_id: int | None,
) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found.")
    if not can_access_exercise(exercise, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Exercise is private.")
    return exercise


def ensure_accessible_exercise_or_400(
    session: Session,
    exercise_id: int | None,
    user_id: int | None,
) -> Exercise:
    if exercise_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exercise_id is required.",
        )

    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected exercise does not exist.",
        )

    if can_access_exercise(exercise, user_id):
        return exercise

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Selected exercise is not accessible.",
    )
