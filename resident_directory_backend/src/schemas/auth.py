from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request payload for admin login."""

    username: str = Field(..., min_length=1, max_length=255, description="Admin username")
    password: str = Field(..., min_length=1, description="Admin password")


class TokenResponse(BaseModel):
    """Response payload containing the issued JWT access token."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")


class MeResponse(BaseModel):
    """Response payload for the current admin identity."""

    username: str = Field(..., description="Authenticated admin username")
