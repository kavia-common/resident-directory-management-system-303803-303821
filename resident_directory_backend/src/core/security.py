import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt
from passlib.context import CryptContext


# bcrypt hashing context (safe default for password hashing)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_jwt_secret() -> str:
    """
    Read JWT_SECRET from environment.

    Raises:
        RuntimeError: If JWT_SECRET is missing/blank.
    """
    secret = os.getenv("JWT_SECRET")
    if not secret or not secret.strip():
        raise RuntimeError(
            "JWT_SECRET environment variable is required but was not set. "
            "Set JWT_SECRET to a long random string."
        )
    return secret.strip()


def _get_jwt_algorithm() -> str:
    """Read JWT_ALGORITHM from environment (defaults to HS256)."""
    return (os.getenv("JWT_ALGORITHM") or "HS256").strip()


def _get_jwt_expires_minutes() -> int:
    """Read JWT_EXPIRES_MINUTES from environment (defaults to 60)."""
    raw = (os.getenv("JWT_EXPIRES_MINUTES") or "60").strip()
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise RuntimeError("JWT_EXPIRES_MINUTES must be an integer.") from exc
    if minutes <= 0:
        raise RuntimeError("JWT_EXPIRES_MINUTES must be > 0.")
    return minutes


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return _pwd_context.verify(plain_password, password_hash)
    except Exception:
        # If hash format is invalid/corrupted, treat as invalid login
        return False


# PUBLIC_INTERFACE
def create_access_token(*, subject: str, expires_minutes: Optional[int] = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: Token subject (we use admin username).
        expires_minutes: Optional override for token expiry window.

    Returns:
        JWT token string.
    """
    expire_minutes = expires_minutes or _get_jwt_expires_minutes()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(payload, _get_jwt_secret(), algorithm=_get_jwt_algorithm())


# PUBLIC_INTERFACE
def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT access token.

    Raises:
        jose.JWTError: If token is invalid/expired.
    """
    return jwt.decode(token, _get_jwt_secret(), algorithms=[_get_jwt_algorithm()])


# PUBLIC_INTERFACE
def extract_subject(token: str) -> str:
    """
    Extract the subject ('sub') from a verified JWT token.

    Raises:
        jose.JWTError: If token invalid/expired.
        ValueError: If subject claim missing/blank.
    """
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if not subject or not isinstance(subject, str) or not subject.strip():
        raise ValueError("Token subject (sub) claim missing.")
    return subject.strip()
