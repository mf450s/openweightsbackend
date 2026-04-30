from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_session
from app.models.exercise import Exercise
from app.models.session import SessionSet, WorkoutSession
from app.models.template import TemplateExercise, TrainingSplit, WorkoutTemplate
from app.models.user import (
    User,
    UserDeleteRequest,
    UserPasswordUpdate,
    UserRead,
    UserSettings,
    UserSettingsPatch,
    UserSettingsRead,
    UserSettingsUpdate,
    UserUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[UserRead])
def list_users(current_user: User = Depends(get_current_user)) -> list[User]:
    return [current_user]


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
def update_current_user(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    updates = payload.model_dump(exclude_unset=True)
    if "email" in updates and updates["email"] != current_user.email:
        existing = session.exec(select(User).where(User.email == updates["email"])).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

    for field_name, value in updates.items():
        setattr(current_user, field_name, value)

    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def update_current_user_password(
    payload: UserPasswordUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    current_user.password_hash = hash_password(payload.new_password)
    session.add(current_user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_or_create_user_settings(session: Session, user_id: int) -> UserSettings:
    settings = session.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(
            user_id=user_id,
            preferences={},
            updated_at=datetime.now(timezone.utc),
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


@router.get("/me/settings", response_model=UserSettingsRead)
def read_current_user_settings(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserSettings:
    return _get_or_create_user_settings(session, current_user.id)


@router.put("/me/settings", response_model=UserSettingsRead)
def replace_current_user_settings(
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserSettings:
    settings = _get_or_create_user_settings(session, current_user.id)
    settings.preferences = payload.preferences
    settings.updated_at = datetime.now(timezone.utc)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


@router.patch("/me/settings", response_model=UserSettingsRead)
def patch_current_user_settings(
    payload: UserSettingsPatch,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserSettings:
    settings = _get_or_create_user_settings(session, current_user.id)
    merged_preferences = dict(settings.preferences)
    merged_preferences.update(payload.preferences)
    settings.preferences = merged_preferences
    settings.updated_at = datetime.now(timezone.utc)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    payload: UserDeleteRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is incorrect.",
        )

    workout_sessions = session.exec(
        select(WorkoutSession).where(WorkoutSession.user_id == current_user.id)
    ).all()
    workout_session_ids = [item.id for item in workout_sessions if item.id is not None]
    if workout_session_ids:
        session_sets = session.exec(
            select(SessionSet).where(SessionSet.session_id.in_(workout_session_ids))
        ).all()
        for session_set in session_sets:
            session.delete(session_set)
    for workout_session in workout_sessions:
        session.delete(workout_session)

    training_splits = session.exec(
        select(TrainingSplit).where(TrainingSplit.user_id == current_user.id)
    ).all()
    split_ids = [item.id for item in training_splits if item.id is not None]
    if split_ids:
        workout_templates = session.exec(
            select(WorkoutTemplate).where(WorkoutTemplate.split_id.in_(split_ids))
        ).all()
        template_ids = [item.id for item in workout_templates if item.id is not None]
        if template_ids:
            template_exercises = session.exec(
                select(TemplateExercise).where(TemplateExercise.template_id.in_(template_ids))
            ).all()
            for template_exercise in template_exercises:
                session.delete(template_exercise)
        for workout_template in workout_templates:
            session.delete(workout_template)
    for training_split in training_splits:
        session.delete(training_split)

    user_settings = session.get(UserSettings, current_user.id)
    if user_settings is not None:
        session.delete(user_settings)

    created_exercises = session.exec(
        select(Exercise).where(Exercise.created_by_user_id == current_user.id)
    ).all()
    for exercise in created_exercises:
        exercise.created_by_user_id = None
        session.add(exercise)

    session.delete(current_user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
