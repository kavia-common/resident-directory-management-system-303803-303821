from datetime import datetime

from pydantic import BaseModel, Field


class AdminBase(BaseModel):
    """Common fields for admin schemas."""

    username: str = Field(..., min_length=1, max_length=255, description="Unique admin username")


class AdminCreate(AdminBase):
    """Payload for creating an admin."""

    password: str = Field(..., min_length=8, description="Plaintext password (will be hashed)")


class AdminOut(AdminBase):
    """Admin representation returned by the API."""

    id: int = Field(..., description="Admin ID")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")

    class Config:
        from_attributes = True
