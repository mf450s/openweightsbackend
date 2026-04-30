from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_session
from app.models.user import User, UserPasswordUpdate, UserRead, UserUpdate

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
