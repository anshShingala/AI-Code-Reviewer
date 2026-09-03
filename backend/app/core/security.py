from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from app.core.config import settings


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    secret_key: str | None = None,
) -> str:
    """Create JWT access token signed with AUTH_SECRET."""
    key = secret_key if secret_key is not None else settings.AUTH_SECRET
    if not key:
        raise ValueError("AUTH_SECRET configuration is missing.")

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=60)

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(to_encode, key, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(
    token: str,
    secret_key: str | None = None,
) -> dict[str, Any] | None:
    """Verify and decode JWT access token."""
    key = secret_key if secret_key is not None else settings.AUTH_SECRET
    if not key:
        return None

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except (jwt.PyJWTError, ValueError):
        return None


# Single-use OAuth state registry to prevent state replay attacks
_USED_OAUTH_STATES: set[str] = set()


def create_oauth_state(
    user_id: str,
    secret_key: str | None = None,
    expires_delta: timedelta | None = None,
    state_type: str | None = None,
) -> str:
    """Create a signed, user-bound, 10-minute expiring OAuth state token."""
    key = secret_key if secret_key is not None else settings.AUTH_SECRET
    if not key:
        raise ValueError("AUTH_SECRET configuration is missing.")

    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else timedelta(minutes=10))

    import secrets
    resolved_type = state_type or ("oauth_login" if user_id == "login" else "oauth_state")
    to_encode: dict[str, Any] = {
        "user_id": str(user_id),
        "nonce": secrets.token_hex(16),
        "iat": now,
        "exp": expire,
        "type": resolved_type,
    }
    return jwt.encode(to_encode, key, algorithm=settings.JWT_ALGORITHM)


def verify_oauth_state(
    state_token: str,
    expected_user_id: str | None = None,
    secret_key: str | None = None,
    expected_state_type: str | None = None,
) -> str | None:
    """Verify OAuth state signature, single-use policy, expiration, and user binding. Returns user_id if valid."""
    if not state_token or state_token in _USED_OAUTH_STATES:
        return None

    key = secret_key if secret_key is not None else settings.AUTH_SECRET
    if not key:
        return None

    try:
        payload = jwt.decode(
            state_token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_type = payload.get("type")
        if token_type not in ("oauth_state", "oauth_login"):
            return None

        if expected_state_type and token_type != expected_state_type:
            return None

        user_id = payload.get("user_id")
        if not user_id:
            return None

        if expected_user_id and str(expected_user_id) != str(user_id):
            return None

        # Mark state as used to prevent replay attacks
        _USED_OAUTH_STATES.add(state_token)
        return str(user_id)
    except (jwt.PyJWTError, ValueError):
        return None
