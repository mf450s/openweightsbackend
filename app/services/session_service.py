from sqlmodel import Session, delete

from app.models.session import SessionSet, WorkoutSession


def delete_workout_session_with_sets(session: Session, workout_session: WorkoutSession) -> None:
    session.exec(delete(SessionSet).where(SessionSet.session_id == workout_session.id))
    session.delete(workout_session)
