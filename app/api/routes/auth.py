from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_session
from app.models.user import AuthToken, LoginRequest, User, UserCreate, UserRead
from app.services.persistence import save_and_refresh

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, session: Session = Depends(get_session)) -> User:
    existing = session.exec(select(User.id).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        email=payload.email,
        name=payload.name,
        default_pause_seconds=payload.default_pause_seconds,
        password_hash=hash_password(payload.password),
    )
    return save_and_refresh(session, user)


@router.post("/login", response_model=AuthToken)
def login_user(
    payload: LoginRequest, session: Session = Depends(get_session)
) -> AuthToken:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing.",
        )

    return AuthToken(
        access_token=create_access_token(user.id),
        user=UserRead.model_validate(user),
    )
