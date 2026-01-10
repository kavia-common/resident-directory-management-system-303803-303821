from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.security import extract_subject, extract_token_type
from src.db.models import Admin
from src.db.session import get_db

_security = HTTPBearer(auto_error=False)


def _raise_unauthorized(detail: str) -> None:
    """Raise a standardized 401."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# PUBLIC_INTERFACE
def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
) -> Admin:
    """
    FastAPI dependency to authenticate an admin via JWT bearer token.

    Behavior:
      - Expects Authorization: Bearer <token>
      - Verifies signature and expiry
      - Ensures token type is 'access'
      - Loads admin by username from DB

    Returns:
        Admin: The authenticated admin ORM object.

    Raises:
        HTTPException(401): If token missing/invalid/expired, wrong type, or admin not found.
    """
    if credentials is None or not credentials.credentials:
        _raise_unauthorized("Not authenticated")

    token = credentials.credentials
    try:
        token_type = extract_token_type(token)
        if token_type != "access":
            _raise_unauthorized("Invalid token type")
        username = extract_subject(token)
    except HTTPException:
        raise
    except Exception:
        _raise_unauthorized("Invalid or expired token")

    admin = db.scalar(select(Admin).where(Admin.username == username))
    if admin is None:
        _raise_unauthorized("Invalid authentication credentials")

    return admin


# PUBLIC_INTERFACE
def require_admin_role(current_admin: Admin = Depends(get_current_admin)) -> Admin:
    """
    FastAPI dependency guard that enforces RBAC 'admin' role.

    Returns:
        Admin: Authenticated admin (role validated).

    Raises:
        HTTPException(403): If authenticated but not an admin.
    """
    if (current_admin.role or "").strip().lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_admin
