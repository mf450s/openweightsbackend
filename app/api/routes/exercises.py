from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.exercise import Exercise, ExerciseCreate, ExerciseRead

router = APIRouter()


@router.get("/", response_model=list[ExerciseRead])
def list_exercises(session: Session = Depends(get_session)) -> list[Exercise]:
    statement = select(Exercise).order_by(Exercise.name)
    return list(session.exec(statement).all())


@router.post("/", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate, session: Session = Depends(get_session)
) -> Exercise:
    existing = session.exec(select(Exercise).where(Exercise.name == payload.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An exercise with this name already exists.",
        )

    exercise = Exercise.model_validate(payload)
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise
