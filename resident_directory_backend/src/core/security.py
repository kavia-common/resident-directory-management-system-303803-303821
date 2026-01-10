import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt
from passlib.context import CryptContext


# bcrypt hashing context (safe default for password hashing)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_jwt_secret() -> str:
    """
    Read JWT secret from environment.

    Preferred env var:
      - JWT_SECRET_KEY

    Backward compatible fallback:
      - JWT_SECRET

    Raises:
        RuntimeError: If secret is missing/blank.
    """
    secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")
    if not secret or not secret.strip():
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required but was not set. "
            "Set JWT_SECRET_KEY to a long random string."
        )
    return secret.strip()


def _get_jwt_algorithm() -> str:
    """Read JWT_ALGORITHM from environment (defaults to HS256)."""
    return (os.getenv("JWT_ALGORITHM") or "HS256").strip()


def _get_access_token_expires_minutes() -> int:
    """
    Read access token expiry minutes from environment (defaults to 60).

    Preferred env var:
      - ACCESS_TOKEN_EXPIRE_MINUTES

    Backward compatible fallback:
      - JWT_EXPIRES_MINUTES
    """
    raw = (
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
        or os.getenv("JWT_EXPIRES_MINUTES")
        or "60"
    ).strip()
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer.") from exc
    if minutes <= 0:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be > 0.")
    return minutes


def _get_refresh_token_expires_days() -> int:
    """
    Read refresh token expiry days from environment (defaults to 14).

    Env var:
      - REFRESH_TOKEN_EXPIRE_DAYS (optional; default 14)
    """
    raw = (os.getenv("REFRESH_TOKEN_EXPIRE_DAYS") or "14").strip()
    try:
        days = int(raw)
    except ValueError as exc:
        raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be an integer.") from exc
    if days <= 0:
        raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be > 0.")
    return days


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
def hash_refresh_token(refresh_token: str) -> str:
    """Hash a refresh token string for storage (bcrypt)."""
    return _pwd_context.hash(refresh_token)


# PUBLIC_INTERFACE
def verify_refresh_token(refresh_token: str, refresh_token_hash: str) -> bool:
    """Verify a refresh token string against stored hash."""
    try:
        return _pwd_context.verify(refresh_token, refresh_token_hash)
    except Exception:
        return False


def _create_token(*, subject: str, token_type: str, expires_delta: timedelta, extra: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT with common claims."""
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload: Dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra:
        payload.update(extra)

    return jwt.encode(payload, _get_jwt_secret(), algorithm=_get_jwt_algorithm())


# PUBLIC_INTERFACE
def create_access_token(*, subject: str, role: Optional[str] = None, expires_minutes: Optional[int] = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: Token subject (admin username).
        role: Optional RBAC role claim.
        expires_minutes: Optional override for token expiry window.

    Returns:
        JWT token string.
    """
    expire_minutes = expires_minutes or _get_access_token_expires_minutes()
    extra: Dict[str, Any] = {}
    if role:
        extra["role"] = role
    return _create_token(subject=subject, token_type="access", expires_delta=timedelta(minutes=expire_minutes), extra=extra)


# PUBLIC_INTERFACE
def create_refresh_token(*, subject: str, role: Optional[str] = None, token_version: int = 0, expires_days: Optional[int] = None) -> str:
    """
    Create a signed JWT refresh token (long-lived).

    Claims:
      - type=refresh
      - role (optional)
      - ver: refresh token version integer (supports invalidating all outstanding refresh tokens)

    Args:
        subject: Admin username.
        role: Optional RBAC role claim.
        token_version: Integer version that must match Admin.refresh_token_version.
        expires_days: Optional override in days.

    Returns:
        JWT refresh token string.
    """
    days = expires_days or _get_refresh_token_expires_days()
    extra: Dict[str, Any] = {"ver": int(token_version)}
    if role:
        extra["role"] = role
    return _create_token(subject=subject, token_type="refresh", expires_delta=timedelta(days=days), extra=extra)


# PUBLIC_INTERFACE
def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT token (access or refresh).

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
    payload = decode_token(token)
    subject = payload.get("sub")
    if not subject or not isinstance(subject, str) or not subject.strip():
        raise ValueError("Token subject (sub) claim missing.")
    return subject.strip()


# PUBLIC_INTERFACE
def extract_token_type(token: str) -> str:
    """Extract token type claim (access|refresh)."""
    payload = decode_token(token)
    t = payload.get("type")
    if not t or not isinstance(t, str):
        raise ValueError("Token type claim missing.")
    return t


# PUBLIC_INTERFACE
def extract_role(token: str) -> Optional[str]:
    """Extract optional role claim from a verified token."""
    payload = decode_token(token)
    role = payload.get("role")
    return role if isinstance(role, str) and role.strip() else None


# PUBLIC_INTERFACE
def extract_refresh_token_version(token: str) -> int:
    """Extract refresh token version claim ('ver') from a verified refresh token."""
    payload = decode_token(token)
    ver = payload.get("ver")
    if ver is None:
        raise ValueError("Refresh token version claim missing.")
    try:
        return int(ver)
    except Exception as exc:
        raise ValueError("Refresh token version claim invalid.") from exc
