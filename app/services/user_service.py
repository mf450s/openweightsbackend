from sqlalchemy import update
from sqlmodel import Session, delete, select

from app.models.exercise import Exercise
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise, TrainingSplit, WorkoutTemplate
from app.models.user import User, UserSettings


def delete_user_related_data(session: Session, user: User) -> None:
    workout_session_ids = select(WorkoutSession.id).where(WorkoutSession.user_id == user.id)
    split_ids = select(TrainingSplit.id).where(TrainingSplit.user_id == user.id)
    template_ids = select(WorkoutTemplate.id).where(WorkoutTemplate.split_id.in_(split_ids))

    session.exec(delete(SessionSet).where(SessionSet.session_id.in_(workout_session_ids)))
    session.exec(delete(WorkoutSession).where(WorkoutSession.user_id == user.id))
    session.exec(delete(TemplateExercise).where(TemplateExercise.template_id.in_(template_ids)))
    session.exec(delete(WorkoutTemplate).where(WorkoutTemplate.split_id.in_(split_ids)))
    session.exec(delete(TrainingSplit).where(TrainingSplit.user_id == user.id))

    user_settings = session.get(UserSettings, user.id)
    if user_settings is not None:
        session.delete(user_settings)

    session.exec(update(Exercise).where(Exercise.created_by_user_id == user.id).values(created_by_user_id=None))

    session.delete(user)
