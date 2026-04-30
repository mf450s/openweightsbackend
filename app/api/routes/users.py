from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlmodel import Session, delete, select

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_session
from app.models.common import utcnow
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
        existing = session.exec(select(User.id).where(User.email == updates["email"])).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

    current_user.sqlmodel_update(updates)
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
            updated_at=utcnow(),
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
    settings.updated_at = utcnow()
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
    settings.updated_at = utcnow()
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

    workout_session_ids = select(WorkoutSession.id).where(WorkoutSession.user_id == current_user.id)
    split_ids = select(TrainingSplit.id).where(TrainingSplit.user_id == current_user.id)
    template_ids = select(WorkoutTemplate.id).where(WorkoutTemplate.split_id.in_(split_ids))

    session.exec(delete(SessionSet).where(SessionSet.session_id.in_(workout_session_ids)))
    session.exec(delete(WorkoutSession).where(WorkoutSession.user_id == current_user.id))
    session.exec(delete(TemplateExercise).where(TemplateExercise.template_id.in_(template_ids)))
    session.exec(delete(WorkoutTemplate).where(WorkoutTemplate.split_id.in_(split_ids)))
    session.exec(delete(TrainingSplit).where(TrainingSplit.user_id == current_user.id))

    user_settings = session.get(UserSettings, current_user.id)
    if user_settings is not None:
        session.delete(user_settings)

    session.exec(
        update(Exercise)
        .where(Exercise.created_by_user_id == current_user.id)
        .values(created_by_user_id=None)
    )

    session.delete(current_user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
