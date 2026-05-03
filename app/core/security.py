import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 100_000
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    encoded_hash = base64.urlsafe_b64encode(password_hash).decode("utf-8")
    return f"{PASSWORD_HASH_SCHEME}${PBKDF2_ITERATIONS}${salt}${encoded_hash}"


def verify_password(password: str, stored_password_hash: str) -> bool:
    try:
        scheme, iterations, salt, encoded_hash = stored_password_hash.split("$", maxsplit=3)
        actual_hash = base64.urlsafe_b64decode(encoded_hash.encode("utf-8"))
        iteration_count = int(iterations)
    except (ValueError, binascii.Error):
        return False

    if scheme != PASSWORD_HASH_SCHEME:
        return False

    expected_hash = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iteration_count,
    )
    return hmac.compare_digest(expected_hash, actual_hash)


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    secret_key = settings.auth_secret_key.get_secret_value()
    expiration = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.auth_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "exp": int(expiration.timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> dict[str, str | int]:
    settings = get_settings()
    secret_key = settings.auth_secret_key.get_secret_value()

    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise ValueError("Invalid token format.") from exc

    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = base64.urlsafe_b64decode(encoded_signature.encode("utf-8"))
        payload_bytes = base64.urlsafe_b64decode(encoded_payload.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid token payload.") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("Invalid token signature.")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise ValueError("Invalid token subject.")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise ValueError("Invalid token expiration.")

    if datetime.now(timezone.utc).timestamp() > expires_at:
        raise ValueError("Token has expired.")

    return payload


def generate_refresh_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    return token, hashed


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
