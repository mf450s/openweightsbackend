from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.session import WorkoutSession, WorkoutSessionCreate, WorkoutSessionRead

router = APIRouter()


@router.get("/", response_model=list[WorkoutSessionRead])
def list_sessions(session: Session = Depends(get_session)) -> list[WorkoutSession]:
    statement = select(WorkoutSession).order_by(WorkoutSession.performed_at.desc())
    return list(session.exec(statement).all())


@router.post("/", response_model=WorkoutSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: WorkoutSessionCreate, session: Session = Depends(get_session)
) -> WorkoutSession:
    workout_session = WorkoutSession.model_validate(payload)
    session.add(workout_session)
    session.commit()
    session.refresh(workout_session)
    return workout_session
