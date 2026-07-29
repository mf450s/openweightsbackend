import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_session
from app.models.user import (
    AuthToken,
    LoginRequest,
    RefreshRequest,
    RefreshToken,
    User,
    UserCreate,
    UserRead,
)
from app.services.persistence import save_and_refresh

router = APIRouter()

# Brute-force protection: IP → list of timestamps of failed login attempts
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 15 * 60


@router.post("/register", response_model=AuthToken, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, session: Session = Depends(get_session)) -> AuthToken:
    existing = session.exec(select(User.id).where(User.email == payload.email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
    )
    user = save_and_refresh(session, user)
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing.",
        )

    settings = get_settings()
    refresh_plain, refresh_hashed = generate_refresh_token()
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        family_id=secrets.token_hex(16),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(refresh_token)
    session.commit()

    return AuthToken(
        access_token=create_access_token(user.id),
        refresh_token=refresh_plain,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=AuthToken)
def login_user(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AuthToken:
    client_ip = request.client.host if request.client else "unknown"

    # --- Brute-force check ---
    now = __import__("time").time()
    attempts = _login_attempts.get(client_ip, [])
    # Prune attempts older than the window
    attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]

    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    # --- End brute-force check ---

    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Record failed attempt
        attempts.append(now)
        _login_attempts[client_ip] = attempts
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

    settings = get_settings()
    refresh_plain, refresh_hashed = generate_refresh_token()
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hashed,
        family_id=secrets.token_hex(16),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(refresh_token)
    session.commit()

    # Successful login resets the counter
    _login_attempts.pop(client_ip, None)

    return AuthToken(
        access_token=create_access_token(user.id),
        refresh_token=refresh_plain,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=AuthToken)
def refresh_token(payload: RefreshRequest, session: Session = Depends(get_session)) -> AuthToken:
    token_hash = hash_refresh_token(payload.refresh_token)

    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()

    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    expires = stored.expires_at.replace(tzinfo=timezone.utc) if stored.expires_at.tzinfo is None else stored.expires_at
    if expires < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )

    if stored.revoked:
        _revoke_all_user_tokens(session, stored.user_id)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )

    stored.revoked = True
    session.add(stored)

    settings = get_settings()
    new_plain, new_hashed = generate_refresh_token()
    new_refresh = RefreshToken(
        user_id=stored.user_id,
        token_hash=new_hashed,
        family_id=stored.family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(new_refresh)
    session.commit()

    user = session.get(User, stored.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User not found.",
        )

    return AuthToken(
        access_token=create_access_token(stored.user_id),
        refresh_token=new_plain,
        user=UserRead.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(payload: RefreshRequest, session: Session = Depends(get_session)) -> Response:
    token_hash = hash_refresh_token(payload.refresh_token)
    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()

    if stored is not None:
        stored.revoked = True
        session.add(stored)
        session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _revoke_all_user_tokens(session: Session, user_id: int) -> None:
    active = session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    ).all()
    for t in active:
        t.revoked = True
    session.add_all(active)
