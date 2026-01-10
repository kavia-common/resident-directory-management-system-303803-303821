from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_current_admin
from src.core.security import (
    create_access_token,
    create_refresh_token,
    extract_refresh_token_version,
    extract_subject,
    extract_token_type,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from src.db.models import Admin
from src.db.session import get_db
from src.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    TokenPairResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="Admin login",
    description="Validate admin credentials and issue JWT access + refresh tokens.",
    operation_id="auth_login",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Authenticate an admin and issue a JWT access + refresh token pair.

    Notes:
      - Access token is short-lived and used for Authorization: Bearer <access_token>.
      - Refresh token is long-lived and used to rotate access tokens.

    Args:
        payload: LoginRequest containing username and password.
        db: Database session dependency.

    Returns:
        TokenPairResponse: access_token, refresh_token, token_type.

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

    access_token = create_access_token(subject=admin.username, role=admin.role)
    refresh_token = create_refresh_token(
        subject=admin.username,
        role=admin.role,
        token_version=int(admin.refresh_token_version or 0),
    )

    # Store hashed refresh token (rotation support)
    admin.refresh_token_hash = hash_refresh_token(refresh_token)
    db.add(admin)
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    summary="Refresh access token",
    description="Rotate refresh token and issue a new access token + refresh token pair.",
    operation_id="auth_refresh",
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Refresh session using a refresh token.

    Security:
      - Validates JWT signature/expiry
      - Ensures token type is 'refresh'
      - Ensures token version matches DB
      - Ensures refresh token matches stored hash (rotation)

    Args:
        payload: RefreshRequest containing refresh_token.
        db: Database session.

    Returns:
        TokenPairResponse: new access + refresh tokens.

    Raises:
        HTTPException(401): If refresh token invalid/expired/revoked.
    """
    token = payload.refresh_token
    try:
        if extract_token_type(token) != "refresh":
            raise ValueError("Wrong token type")
        username = extract_subject(token)
        ver = extract_refresh_token_version(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    admin = db.scalar(select(Admin).where(Admin.username == username))
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if int(admin.refresh_token_version or 0) != int(ver):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    if not admin.refresh_token_hash or not verify_refresh_token(token, str(admin.refresh_token_hash)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    # Rotate: issue new refresh token, store its hash
    access_token = create_access_token(subject=admin.username, role=admin.role)
    new_refresh_token = create_refresh_token(
        subject=admin.username,
        role=admin.role,
        token_version=int(admin.refresh_token_version or 0),
    )
    admin.refresh_token_hash = hash_refresh_token(new_refresh_token)
    db.add(admin)
    db.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=new_refresh_token, token_type="bearer")


@router.post(
    "/logout",
    summary="Logout (revoke refresh tokens)",
    description="Revoke refresh tokens by bumping refresh_token_version and clearing stored refresh token hash.",
    operation_id="auth_logout",
)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> dict:
    """
    Logout by revoking refresh tokens.

    This implementation revokes refresh tokens by:
      - bumping Admin.refresh_token_version (invalidates all existing refresh JWTs)
      - clearing Admin.refresh_token_hash

    Args:
        payload: LogoutRequest containing refresh_token (used only to identify the admin).
        db: Database session.

    Returns:
        { "ok": true }

    Raises:
        HTTPException(401): If refresh token invalid.
    """
    token = payload.refresh_token
    try:
        if extract_token_type(token) != "refresh":
            raise ValueError("Wrong token type")
        username = extract_subject(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    admin = db.scalar(select(Admin).where(Admin.username == username))
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    admin.refresh_token_version = int(admin.refresh_token_version or 0) + 1
    admin.refresh_token_hash = None
    db.add(admin)
    db.commit()

    return {"ok": True}


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current admin identity",
    description="Return the current authenticated admin username and role.",
    operation_id="auth_me",
)
def me(current_admin: Admin = Depends(get_current_admin)) -> MeResponse:
    """
    Return info about the currently authenticated admin.

    Args:
        current_admin: Admin loaded by get_current_admin dependency.

    Returns:
        MeResponse: Current admin username + role.
    """
    return MeResponse(username=current_admin.username, role=current_admin.role)
