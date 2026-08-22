from sqlalchemy import update
from sqlmodel import Session, delete, select

from app.models.exercise import Exercise
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise, TrainingSplit, WorkoutTemplate
from app.models.user import RefreshToken, User, UserSettings


def delete_user_aggregate(session: Session, user: User) -> None:
    """Stage the complete account aggregate deletion in the caller's transaction.

    No commit is performed here: the route owns the transaction so any failure
    rolls back the anonymization and every dependent-row deletion together.
    """
    user_id = user.id
    workout_session_ids = select(WorkoutSession.id).where(WorkoutSession.user_id == user_id)
    split_ids = select(TrainingSplit.id).where(TrainingSplit.user_id == user_id)
    template_ids = select(WorkoutTemplate.id).where(
        (WorkoutTemplate.user_id == user_id) | WorkoutTemplate.split_id.in_(split_ids)
    )

    session.exec(delete(SessionSet).where(SessionSet.session_id.in_(workout_session_ids)))
    session.exec(delete(WorkoutSession).where(WorkoutSession.user_id == user_id))
    session.exec(delete(TemplateExercise).where(TemplateExercise.template_id.in_(template_ids)))
    session.exec(delete(WorkoutTemplate).where(WorkoutTemplate.id.in_(template_ids)))
    session.exec(delete(TrainingSplit).where(TrainingSplit.user_id == user_id))
    session.exec(delete(RefreshToken).where(RefreshToken.user_id == user_id))

    user_settings = session.get(UserSettings, user_id)
    if user_settings is not None:
        session.delete(user_settings)

    session.exec(
        update(Exercise)
        .where(Exercise.created_by_user_id == user_id)
        .values(created_by_user_id=None)
    )
    session.delete(user)


# Backwards-compatible internal name for callers outside the route module.
delete_user_related_data = delete_user_aggregate
