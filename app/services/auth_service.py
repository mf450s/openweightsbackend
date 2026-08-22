import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from app.models.user import AuthToken, RefreshToken, User, UserRead


def issue_tokens(session: Session, user: User, *, family_id: str | None = None) -> AuthToken:
    if user.id is None:
        raise HTTPException(status_code=500, detail="User ID is missing.")
    settings = get_settings()
    refresh_plain, refresh_hashed = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hashed,
            family_id=family_id or secrets.token_hex(16),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    session.commit()
    return AuthToken(
        access_token=create_access_token(user.id),
        refresh_token=refresh_plain,
        user=UserRead.model_validate(user),
    )


def rotate_refresh_token(session: Session, plain_token: str) -> AuthToken:
    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(plain_token))).first()
    if stored is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    expires = stored.expires_at.replace(tzinfo=timezone.utc) if stored.expires_at.tzinfo is None else stored.expires_at
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired.")
    if stored.revoked:
        revoke_all(session, stored.user_id)
        session.commit()
        raise HTTPException(status_code=401, detail="Refresh token has been revoked.")
    user = session.get(User, stored.user_id)
    if user is None:
        raise HTTPException(status_code=500, detail="User not found.")
    stored.revoked = True
    session.add(stored)
    # issue_tokens commits the rotation atomically with the new token.
    return issue_tokens(session, user, family_id=stored.family_id)


def logout(session: Session, plain_token: str) -> None:
    stored = session.exec(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(plain_token))).first()
    if stored is not None:
        stored.revoked = True
        session.add(stored)
        session.commit()


def revoke_all(session: Session, user_id: int) -> None:
    active = session.exec(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)).all()
    for token in active:
        token.revoked = True
    session.add_all(active)
