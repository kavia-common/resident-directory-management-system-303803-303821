from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_current_admin
from src.core.security import create_access_token, verify_password
from src.db.models import Admin
from src.db.session import get_db
from src.schemas.auth import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Admin login",
    description="Validate admin credentials and issue a JWT access token.",
    operation_id="auth_login",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Authenticate an admin and issue a JWT access token.

    Args:
        payload: LoginRequest containing username and password.
        db: Database session dependency.

    Returns:
        TokenResponse: JWT access token and token type.

    Raises:
        HTTPException(401): If username/password is invalid.
    """
    admin = db.scalar(select(Admin).where(Admin.username == payload.username))
    if admin is None or not verify_password(payload.password, admin.password_hash):
        # Do not reveal whether username exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=admin.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current admin identity",
    description="Return the current authenticated admin username.",
    operation_id="auth_me",
)
def me(current_admin: Admin = Depends(get_current_admin)) -> MeResponse:
    """
    Return info about the currently authenticated admin.

    Args:
        current_admin: Admin loaded by get_current_admin dependency.

    Returns:
        MeResponse: Current admin username.
    """
    return MeResponse(username=current_admin.username)
