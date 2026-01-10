from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request payload for admin login."""

    username: str = Field(..., min_length=1, max_length=255, description="Admin username")
    password: str = Field(..., min_length=1, description="Admin password")


class RefreshRequest(BaseModel):
    """Request payload for refresh token rotation."""

    refresh_token: str = Field(..., min_length=1, description="JWT refresh token")


class LogoutRequest(BaseModel):
    """Request payload for logout (revokes refresh tokens)."""

    refresh_token: str = Field(..., min_length=1, description="JWT refresh token to revoke")


class TokenPairResponse(BaseModel):
    """Response payload containing issued access + refresh tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")


class TokenResponse(BaseModel):
    """Response payload containing the issued JWT access token."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")


class MeResponse(BaseModel):
    """Response payload for the current admin identity."""

    username: str = Field(..., description="Authenticated admin username")
    role: str = Field(..., description="Authenticated admin role (RBAC)")
