import base64
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import SQLModel

from app.api.deps import (
    UNAUTHORIZED_EXCEPTION,
    _get_user_from_credentials,
    get_current_user,
    get_optional_current_user,
)
from app.core.config import get_settings
from app.core.security import (
    PASSWORD_HASH_SCHEME,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import engine, get_session
from app.models.user import User


def test_hash_and_verify_password_variants():
    password = "verysecret"
    stored = hash_password(password)

    assert verify_password(password, stored) is True
    assert verify_password("wrong", stored) is False
    assert verify_password(password, "bad-format") is False

    wrong_scheme = stored.replace(PASSWORD_HASH_SCHEME, "sha1", 1)
    assert verify_password(password, wrong_scheme) is False


def test_access_token_roundtrip_and_invalid_format():
    token = create_access_token(user_id=123, expires_delta=timedelta(minutes=5))
    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert isinstance(payload["exp"], int)

    with pytest.raises(ValueError, match="Invalid token format"):
        decode_access_token("not-a-valid-token")


def _build_token_with_payload(payload: dict, signature_payload: str | None = None) -> str:
    settings = get_settings()
    secret_key = settings.auth_secret_key.get_secret_value()

    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("utf-8")
    to_sign = signature_payload or encoded_payload
    signature = hmac.new(
        secret_key.encode("utf-8"),
        to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{encoded_payload}.{encoded_signature}"


def test_decode_access_token_validation_paths():
    valid = create_access_token(user_id=1, expires_delta=timedelta(minutes=5))
    encoded_payload, encoded_signature = valid.split(".", maxsplit=1)

    with pytest.raises(ValueError, match="Invalid token payload"):
        decode_access_token(f"%%% .{encoded_signature}".replace(" ", ""))

    tampered_payload = base64.urlsafe_b64encode(
        json.dumps({"sub": "1", "exp": 9_999_999_999}).encode("utf-8")
    ).decode("utf-8")
    with pytest.raises(ValueError, match="Invalid token signature"):
        decode_access_token(f"{tampered_payload}.{encoded_signature}")

    no_subject = _build_token_with_payload({"sub": "", "exp": 9_999_999_999})
    with pytest.raises(ValueError, match="Invalid token subject"):
        decode_access_token(no_subject)

    bad_exp_type = _build_token_with_payload({"sub": "1", "exp": "tomorrow"})
    with pytest.raises(ValueError, match="Invalid token expiration"):
        decode_access_token(bad_exp_type)

    expired = _build_token_with_payload({"sub": "1", "exp": 1})
    with pytest.raises(ValueError, match="Token has expired"):
        decode_access_token(expired)


def test_get_user_from_credentials_unauthorized_paths(session):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="definitely-invalid")

    with pytest.raises(HTTPException) as invalid_token_exc:
        _get_user_from_credentials(creds, session)
    assert invalid_token_exc.value.status_code == UNAUTHORIZED_EXCEPTION.status_code

    token_missing_user = create_access_token(user_id=9999)
    missing_user_creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=token_missing_user
    )
    with pytest.raises(HTTPException) as missing_user_exc:
        _get_user_from_credentials(missing_user_creds, session)
    assert missing_user_exc.value.status_code == UNAUTHORIZED_EXCEPTION.status_code


def test_current_user_helpers(session):
    user = User(
        name="Helper User",
        email="helper@example.com",
        password_hash=hash_password("secret"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user.id)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    current = get_current_user(credentials=creds, session=session)
    assert current.id == user.id

    optional_none = get_optional_current_user(credentials=None, session=session)
    assert optional_none is None


def test_get_current_user_requires_credentials(session):
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=None, session=session)
    assert exc.value.status_code == 401


def test_get_session_yields_sqlmodel_session():
    SQLModel.metadata.create_all(engine)
    session_gen = get_session()
    session = next(session_gen)
    try:
        assert session.bind is not None
    finally:
        with pytest.raises(StopIteration):
            next(session_gen)
    SQLModel.metadata.drop_all(engine)
