from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ResidentBase(BaseModel):
    """Common fields for resident schemas."""

    name: str = Field(..., min_length=1, max_length=255, description="Resident full name")
    address: str = Field(..., min_length=1, description="Resident address")
    phone: str = Field(..., min_length=1, max_length=50, description="Resident phone number")
    email: EmailStr = Field(..., description="Resident email address")

    building: Optional[str] = Field(None, max_length=100, description="Optional building name/identifier")
    unit: Optional[str] = Field(None, max_length=50, description="Optional unit/apartment identifier")

    photo_url: Optional[str] = Field(None, description="Optional URL to resident photo")


class ResidentCreate(ResidentBase):
    """Payload for creating a resident."""


class ResidentUpdate(BaseModel):
    """Payload for partially updating a resident."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Resident full name")
    address: Optional[str] = Field(None, min_length=1, description="Resident address")
    phone: Optional[str] = Field(None, min_length=1, max_length=50, description="Resident phone number")
    email: Optional[EmailStr] = Field(None, description="Resident email address")
    photo_url: Optional[str] = Field(None, description="Optional URL to resident photo")


class ResidentOut(ResidentBase):
    """Resident representation returned by the API."""

    id: int = Field(..., description="Resident ID")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")

    class Config:
        from_attributes = True
