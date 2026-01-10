from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from src.schemas.resident import ResidentOut


class ResidentSortField(str, Enum):
    """Allowed sort fields for resident listings."""

    id = "id"
    name = "name"
    email = "email"
    phone = "phone"
    building = "building"
    unit = "unit"
    updated_at = "updated_at"
    created_at = "created_at"


class SortDirection(str, Enum):
    """Allowed sort directions."""

    asc = "asc"
    desc = "desc"


class ResidentListQuery(BaseModel):
    """
    Query model for listing/exporting residents with optional filters.

    Notes:
      - All fields are optional; only provided filters are applied.
      - `name` is partial and case-insensitive.
      - `updated_at_from`/`updated_at_to` define an inclusive range.
    """

    q: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional search applied to name/address/phone/email/building/unit (case-insensitive).",
        examples=["smith", "Unit 10"],
    )

    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional name filter (partial match, case-insensitive).",
        examples=["john"],
    )
    building: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional building filter (exact match).",
        examples=["A", "Tower 2"],
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional unit filter (exact match).",
        examples=["12B"],
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional phone filter (exact match).",
        examples=["+1-555-0100"],
    )
    email: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional email filter (exact match, case-insensitive).",
        examples=["jane@example.com"],
    )

    updated_at_from: Optional[datetime] = Field(
        default=None,
        description="Optional start of updated_at range (inclusive). RFC3339 timestamp.",
        examples=["2025-01-01T00:00:00Z"],
    )
    updated_at_to: Optional[datetime] = Field(
        default=None,
        description="Optional end of updated_at range (inclusive). RFC3339 timestamp.",
        examples=["2025-12-31T23:59:59Z"],
    )

    sort_by: ResidentSortField = Field(
        default=ResidentSortField.id,
        description="Sort field.",
        examples=["updated_at", "name"],
    )
    sort_dir: SortDirection = Field(
        default=SortDirection.asc,
        description="Sort direction.",
        examples=["desc"],
    )

    page: int = Field(default=1, ge=1, description="1-based page index.", examples=[1])
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100).", examples=[20])

    @model_validator(mode="after")
    def _validate_ranges(self) -> "ResidentListQuery":
        """
        Validate cross-field constraints for list/search query.

        Ensures:
          - updated_at_from <= updated_at_to when both are provided
        """
        if self.updated_at_from and self.updated_at_to and self.updated_at_from > self.updated_at_to:
            raise ValueError("updated_at_from must be <= updated_at_to")
        return self


class ResidentListResponse(BaseModel):
    """Paginated listing response."""

    items: List[ResidentOut] = Field(..., description="List of residents.")
    page: int = Field(..., description="Current page (1-based).", examples=[1])
    page_size: int = Field(..., description="Page size.", examples=[20])
    total: int = Field(..., description="Total rows matching filters.", examples=[123])


class CsvImportRowError(BaseModel):
    """A per-row validation/upsert error returned by CSV import."""

    row_number: int = Field(..., description="1-based row number in the CSV (excluding header).", examples=[3])
    message: str = Field(..., description="Human readable error message.", examples=["Missing required field: name"])
    raw: Optional[dict] = Field(default=None, description="Optional raw row data for debugging.")


class CsvImportReport(BaseModel):
    """Structured report returned by the CSV import endpoint."""

    created: int = Field(..., ge=0, description="Number of newly created residents.", examples=[10])
    updated: int = Field(..., ge=0, description="Number of updated residents.", examples=[5])
    skipped: int = Field(..., ge=0, description="Number of skipped rows (e.g., duplicates or empty rows).", examples=[2])
    errors: List[CsvImportRowError] = Field(
        default_factory=list,
        description="List of per-row errors; import continues even if some rows fail.",
        examples=[
            [
                {
                    "row_number": 2,
                    "message": "Invalid email: not-an-email",
                    "raw": {"name": "John Smith", "email": "not-an-email"},
                }
            ]
        ],
    )
