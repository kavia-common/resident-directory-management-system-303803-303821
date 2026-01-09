from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.security import extract_subject
from src.db.models import Admin
from src.db.session import get_db

_security = HTTPBearer(auto_error=False)


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
      - Loads admin by username from DB

    Returns:
        Admin: The authenticated admin ORM object.

    Raises:
        HTTPException(401): If token missing/invalid/expired or admin not found.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        username = extract_subject(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin = db.scalar(select(Admin).where(Admin.username == username))
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return admin
