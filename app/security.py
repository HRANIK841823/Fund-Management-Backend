from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import settings

_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password, password_hash)
    except Exception:
        return False


# Used to burn the same CPU time when a login names a user that doesn't exist.
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id inside a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
