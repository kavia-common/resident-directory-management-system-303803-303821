from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import EmailStr
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.api.deps import get_current_admin
from src.db.models import Admin, Resident
from src.db.session import get_db
from src.schemas.resident import ResidentCreate, ResidentOut, ResidentUpdate
from src.schemas.resident_search import (
    CsvImportReport,
    CsvImportRowError,
    ResidentListResponse,
    ResidentSortField,
    SortDirection,
)

router = APIRouter(prefix="/residents", tags=["residents"])

# CSV headers for import/export
_REQUIRED_IMPORT_HEADERS = ["name", "address", "phone", "email", "building", "unit"]
_OPTIONAL_IMPORT_HEADERS = ["photo_url"]
_ALL_IMPORT_HEADERS = _REQUIRED_IMPORT_HEADERS + _OPTIONAL_IMPORT_HEADERS

_EXPORT_HEADERS = [
    "id",
    "name",
    "address",
    "phone",
    "email",
    "building",
    "unit",
    "photo_url",
    "created_at",
    "updated_at",
]


def _strip_or_none(val: Optional[str]) -> Optional[str]:
    """Normalize incoming string values (trim; turn blanks into None)."""
    if val is None:
        return None
    v = str(val).strip()
    return v if v else None


def _apply_text_search(stmt, q: Optional[str]):
    """
    Apply case-insensitive search across resident fields.

    This is the existing behavior, extended to also search building/unit if present.
    We use ILIKE which is supported by PostgreSQL.
    """
    if not q:
        return stmt

    query = q.strip()
    if not query:
        return stmt

    pattern = f"%{query}%"
    return stmt.where(
        or_(
            Resident.name.ilike(pattern),
            Resident.address.ilike(pattern),
            Resident.phone.ilike(pattern),
            Resident.email.ilike(pattern),
            Resident.building.ilike(pattern),
            Resident.unit.ilike(pattern),
        )
    )


def _apply_advanced_filters(
    stmt,
    *,
    name: Optional[str],
    building: Optional[str],
    unit: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    updated_at_from: Optional[datetime],
    updated_at_to: Optional[datetime],
):
    """
    Apply optional advanced filters.

    Index-friendliness notes:
      - For exact filters (building/unit/phone), use equality which can leverage btree indexes.
      - For email, we use lower(email)=lower(:email) to preserve case-insensitivity, which can
        be made index-friendly via a functional index on lower(email) in Postgres.
      - For name partial match, we use ILIKE; for best performance at scale, a trigram index
        can be added (pg_trgm).
    """
    if name:
        pattern = f"%{name.strip()}%"
        if name.strip():
            stmt = stmt.where(Resident.name.ilike(pattern))

    if building:
        stmt = stmt.where(Resident.building == building.strip())

    if unit:
        stmt = stmt.where(Resident.unit == unit.strip())

    if phone:
        stmt = stmt.where(Resident.phone == phone.strip())

    if email:
        e = email.strip()
        stmt = stmt.where(func.lower(Resident.email) == func.lower(e))

    if updated_at_from is not None:
        stmt = stmt.where(Resident.updated_at >= updated_at_from)

    if updated_at_to is not None:
        stmt = stmt.where(Resident.updated_at <= updated_at_to)

    return stmt


def _apply_sort(stmt, *, sort_by: ResidentSortField, sort_dir: SortDirection):
    """Apply safe server-side sorting based on a whitelist of sortable fields."""
    sort_map = {
        ResidentSortField.id: Resident.id,
        ResidentSortField.name: Resident.name,
        ResidentSortField.email: Resident.email,
        ResidentSortField.phone: Resident.phone,
        ResidentSortField.building: Resident.building,
        ResidentSortField.unit: Resident.unit,
        ResidentSortField.updated_at: Resident.updated_at,
        ResidentSortField.created_at: Resident.created_at,
    }
    col = sort_map.get(sort_by, Resident.id)
    if sort_dir == SortDirection.desc:
        return stmt.order_by(col.desc())
    return stmt.order_by(col.asc())


def _build_filtered_stmt(
    *,
    q: Optional[str],
    name: Optional[str],
    building: Optional[str],
    unit: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    updated_at_from: Optional[datetime],
    updated_at_to: Optional[datetime],
    sort_by: ResidentSortField,
    sort_dir: SortDirection,
):
    """Create a base SELECT statement with all filters + sort applied (no offset/limit)."""
    stmt = select(Resident)
    stmt = _apply_text_search(stmt, q)
    stmt = _apply_advanced_filters(
        stmt,
        name=name,
        building=building,
        unit=unit,
        phone=phone,
        email=email,
        updated_at_from=updated_at_from,
        updated_at_to=updated_at_to,
    )
    stmt = _apply_sort(stmt, sort_by=sort_by, sort_dir=sort_dir)
    return stmt


def _count_total(db: Session, filtered_stmt) -> int:
    """Count total rows for a filtered statement."""
    # Turn SELECT Resident ... into SELECT count(*) FROM ( ... ) subquery
    subq = filtered_stmt.order_by(None).subquery()
    return int(db.scalar(select(func.count()).select_from(subq)) or 0)


def _iter_csv_rows(file_obj: io.TextIOBase) -> Iterable[Tuple[int, Dict[str, str]]]:
    """
    Yield (row_number, row_dict) from a CSV file-like object.

    Row numbers are 1-based excluding header.
    """
    reader = csv.DictReader(file_obj)
    for idx, row in enumerate(reader, start=1):
        yield idx, row


def _validate_import_headers(fieldnames: Optional[Sequence[str]]) -> List[str]:
    """Return missing headers list (empty means ok)."""
    if not fieldnames:
        return _REQUIRED_IMPORT_HEADERS
    have = {h.strip() for h in fieldnames if h is not None}
    missing = [h for h in _REQUIRED_IMPORT_HEADERS if h not in have]
    return missing


def _normalize_row(row: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Trim values and return a normalized dict with known keys."""
    normalized: Dict[str, Optional[str]] = {}
    for key in _ALL_IMPORT_HEADERS:
        normalized[key] = _strip_or_none(row.get(key))
    return normalized


def _find_existing_for_upsert(
    db: Session,
    *,
    name: Optional[str],
    unit: Optional[str],
    email: Optional[str],
) -> Optional[Resident]:
    """
    Find a resident to update ("upsert target") using natural keys:
      1) If email present: match by case-insensitive email
      2) Else if name+unit present: match by exact name and exact unit
    """
    if email:
        return db.scalar(select(Resident).where(func.lower(Resident.email) == func.lower(email)))

    if name and unit:
        return db.scalar(select(Resident).where(and_(Resident.name == name, Resident.unit == unit)))

    return None


@router.get(
    "",
    response_model=ResidentListResponse,
    summary="List residents (advanced filters + pagination)",
    description=(
        "Return a paginated list of residents. Requires admin authentication.\n\n"
        "Filters (all optional):\n"
        "- `q`: case-insensitive partial search across name/address/phone/email/building/unit\n"
        "- `name`: partial case-insensitive match\n"
        "- `building`, `unit`, `phone`: exact match\n"
        "- `email`: exact match (case-insensitive)\n"
        "- `updated_at_from`, `updated_at_to`: inclusive RFC3339 datetime range\n\n"
        "Sorting:\n"
        "- `sort_by`: one of id,name,email,phone,building,unit,created_at,updated_at\n"
        "- `sort_dir`: asc|desc\n\n"
        "Pagination:\n"
        "- `page` is 1-based\n"
        "- `page_size` capped to 100\n"
    ),
    operation_id="residents_list",
)
def list_residents(
    q: Optional[str] = Query(
        default=None,
        description="Optional text search (case-insensitive partial match).",
        max_length=200,
        examples=["smith"],
    ),
    name: Optional[str] = Query(
        default=None,
        description="Optional name filter (partial, case-insensitive).",
        max_length=255,
        examples=["john"],
    ),
    building: Optional[str] = Query(
        default=None,
        description="Optional building filter (exact match).",
        max_length=100,
        examples=["A"],
    ),
    unit: Optional[str] = Query(
        default=None,
        description="Optional unit filter (exact match).",
        max_length=50,
        examples=["12B"],
    ),
    phone: Optional[str] = Query(
        default=None,
        description="Optional phone filter (exact match).",
        max_length=50,
        examples=["+1-555-0100"],
    ),
    email: Optional[str] = Query(
        default=None,
        description="Optional email filter (exact match, case-insensitive).",
        max_length=255,
        examples=["jane@example.com"],
    ),
    updated_at_from: Optional[datetime] = Query(
        default=None,
        description="Optional updated_at lower bound (inclusive). RFC3339 datetime.",
        examples=["2025-01-01T00:00:00Z"],
    ),
    updated_at_to: Optional[datetime] = Query(
        default=None,
        description="Optional updated_at upper bound (inclusive). RFC3339 datetime.",
        examples=["2025-12-31T23:59:59Z"],
    ),
    sort_by: ResidentSortField = Query(
        default=ResidentSortField.id,
        description="Sort field.",
        examples=["updated_at"],
    ),
    sort_dir: SortDirection = Query(
        default=SortDirection.asc,
        description="Sort direction.",
        examples=["desc"],
    ),
    page: int = Query(1, ge=1, description="1-based page index.", examples=[1]),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100).", examples=[20]),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> ResidentListResponse:
    """
    List residents with optional filters, sorting, and pagination.

    Args:
        q: Optional broad search query.
        name: Optional partial name filter (case-insensitive).
        building: Optional exact building filter.
        unit: Optional exact unit filter.
        phone: Optional exact phone filter.
        email: Optional exact email filter (case-insensitive).
        updated_at_from: Optional inclusive updated_at start datetime.
        updated_at_to: Optional inclusive updated_at end datetime.
        sort_by: Sort field.
        sort_dir: Sort direction.
        page: 1-based page index.
        page_size: Page size (max 100).
        db: Database session dependency.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        ResidentListResponse containing items and pagination metadata.
    """
    _ = current_admin  # auth guard

    base_stmt = _build_filtered_stmt(
        q=q,
        name=name,
        building=building,
        unit=unit,
        phone=phone,
        email=email,
        updated_at_from=updated_at_from,
        updated_at_to=updated_at_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    total = _count_total(db, base_stmt)
    offset = (page - 1) * page_size
    stmt = base_stmt.offset(offset).limit(page_size)
    residents = db.scalars(stmt).all()

    return ResidentListResponse(items=residents, page=page, page_size=page_size, total=total)


@router.get(
    "/export",
    summary="Export residents to CSV (admin only)",
    description=(
        "Export residents as a CSV file with headers. Supports the same filters as GET /residents.\n\n"
        "Response is `text/csv` with UTF-8 encoding."
    ),
    operation_id="residents_export_csv",
    responses={
        200: {
            "content": {"text/csv": {"example": "id,name,address,phone,email,building,unit,photo_url,created_at,updated_at\n1,Jane Doe,..."}}
        }
    },
)
def export_residents_csv(
    q: Optional[str] = Query(default=None, max_length=200, description="Optional text search.", examples=["smith"]),
    name: Optional[str] = Query(default=None, max_length=255, description="Optional name partial filter."),
    building: Optional[str] = Query(default=None, max_length=100, description="Optional building exact filter."),
    unit: Optional[str] = Query(default=None, max_length=50, description="Optional unit exact filter."),
    phone: Optional[str] = Query(default=None, max_length=50, description="Optional phone exact filter."),
    email: Optional[str] = Query(default=None, max_length=255, description="Optional email exact filter."),
    updated_at_from: Optional[datetime] = Query(default=None, description="updated_at lower bound (inclusive)."),
    updated_at_to: Optional[datetime] = Query(default=None, description="updated_at upper bound (inclusive)."),
    sort_by: ResidentSortField = Query(default=ResidentSortField.id, description="Sort field."),
    sort_dir: SortDirection = Query(default=SortDirection.asc, description="Sort direction."),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> Response:
    """
    Export filtered residents as a CSV.

    Args:
        Same filters as list endpoint.
        db: Database session.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        A FastAPI Response with text/csv content.
    """
    _ = current_admin

    stmt = _build_filtered_stmt(
        q=q,
        name=name,
        building=building,
        unit=unit,
        phone=phone,
        email=email,
        updated_at_from=updated_at_from,
        updated_at_to=updated_at_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    residents = db.scalars(stmt).all()

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_EXPORT_HEADERS)
    writer.writeheader()

    for r in residents:
        writer.writerow(
            {
                "id": r.id,
                "name": r.name,
                "address": r.address,
                "phone": r.phone,
                "email": r.email,
                "building": getattr(r, "building", None) or "",
                "unit": getattr(r, "unit", None) or "",
                "photo_url": r.photo_url or "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            }
        )

    filename = f"residents_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/import",
    response_model=CsvImportReport,
    summary="Import residents from CSV (admin only)",
    description=(
        "Import residents from a CSV file uploaded as multipart/form-data.\n\n"
        "Headers:\n"
        "- required: name,address,phone,email,building,unit\n"
        "- optional: photo_url\n\n"
        "Upsert behavior:\n"
        "- If email is present: upsert by case-insensitive email.\n"
        "- Else: upsert by (name + unit).\n\n"
        "Returns a report with counts and per-row errors; import continues even if some rows fail."
    ),
    operation_id="residents_import_csv",
)
async def import_residents_csv(
    file: UploadFile = File(..., description="CSV file containing resident rows."),
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> CsvImportReport:
    """
    Import residents from CSV with per-row validation and upsert.

    Args:
        file: Uploaded CSV file (multipart/form-data).
        db: Database session.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        CsvImportReport: created/updated/skipped counts plus per-row errors.

    Raises:
        HTTPException(400): On invalid CSV format/headers.
    """
    _ = current_admin

    # Basic content-type safety (still accept unknowns because browsers vary)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a .csv file.")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handle BOM if present
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded.",
        )

    buf = io.StringIO(text)
    reader = csv.DictReader(buf)

    missing = _validate_import_headers(reader.fieldnames)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required CSV headers: {', '.join(missing)}",
        )

    report = CsvImportReport(created=0, updated=0, skipped=0, errors=[])

    # Process rows
    for row_number, raw_row in _iter_csv_rows(io.StringIO(text)):
        # DictReader consumes header each time; we need a reader per loop if we use helper.
        # So we re-parse once with a stable iterator:
        # (This block is never used because _iter_csv_rows() isn't called here.)
        _ = row_number
        _ = raw_row

    # Re-iterate using the original reader
    buf2 = io.StringIO(text)
    reader2 = csv.DictReader(buf2)

    for row_number, row in enumerate(reader2, start=1):
        try:
            normalized = _normalize_row(row)

            # Skip completely empty rows
            if not any(normalized.get(k) for k in _ALL_IMPORT_HEADERS):
                report.skipped += 1
                continue

            # Required validations
            for req in _REQUIRED_IMPORT_HEADERS:
                if not normalized.get(req):
                    raise ValueError(f"Missing required field: {req}")

            # Validate email format using Pydantic EmailStr
            email_str = normalized["email"]
            try:
                _ = EmailStr._validate(email_str)  # type: ignore[attr-defined]
            except Exception as exc:
                raise ValueError(f"Invalid email: {email_str}") from exc

            name = normalized["name"]
            unit = normalized["unit"]
            email = normalized["email"]

            existing = _find_existing_for_upsert(db, name=name, unit=unit, email=email)

            if existing is None:
                resident = Resident(
                    name=name,
                    address=normalized["address"],
                    phone=normalized["phone"],
                    email=email,
                    building=normalized["building"],
                    unit=normalized["unit"],
                    photo_url=normalized.get("photo_url"),
                )
                db.add(resident)
                report.created += 1
            else:
                # Update fields
                existing.name = name
                existing.address = normalized["address"]
                existing.phone = normalized["phone"]
                existing.email = email
                existing.building = normalized["building"]
                existing.unit = normalized["unit"]
                existing.photo_url = normalized.get("photo_url")
                db.add(existing)
                report.updated += 1

        except Exception as exc:
            report.errors.append(
                CsvImportRowError(
                    row_number=row_number,
                    message=str(exc),
                    raw={k: row.get(k) for k in (reader2.fieldnames or [])},
                )
            )

    # Commit once at the end (atomic for successful rows)
    db.commit()
    return report


@router.get(
    "/{resident_id}",
    response_model=ResidentOut,
    summary="Get a resident by ID",
    description="Fetch a single resident record by ID. Requires admin authentication.",
    operation_id="residents_get",
)
def get_resident(
    resident_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> ResidentOut:
    """
    Get a resident by ID.

    Args:
        resident_id: Resident ID.
        db: Database session dependency.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        The resident record.

    Raises:
        HTTPException(404): If resident does not exist.
    """
    _ = current_admin

    resident = db.get(Resident, resident_id)
    if resident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resident not found")
    return resident


@router.post(
    "",
    response_model=ResidentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a resident",
    description="Create a new resident record. Requires admin authentication.",
    operation_id="residents_create",
)
def create_resident(
    payload: ResidentCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> ResidentOut:
    """
    Create a resident.

    Args:
        payload: ResidentCreate payload.
        db: Database session dependency.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        The created resident.

    Notes:
        Uses commit + refresh to populate autogenerated fields (id, timestamps).
    """
    _ = current_admin

    resident = Resident(
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
        email=str(payload.email),
        building=payload.building,
        unit=payload.unit,
        photo_url=payload.photo_url,
    )
    db.add(resident)
    db.commit()
    db.refresh(resident)
    return resident


@router.put(
    "/{resident_id}",
    response_model=ResidentOut,
    summary="Update a resident",
    description=(
        "Update an existing resident record by ID. Requires admin authentication.\n\n"
        "This is a partial update: only provided fields are modified."
    ),
    operation_id="residents_update",
)
def update_resident(
    resident_id: int,
    payload: ResidentUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> ResidentOut:
    """
    Update a resident.

    Args:
        resident_id: Resident ID.
        payload: ResidentUpdate payload (partial fields).
        db: Database session dependency.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        The updated resident.

    Raises:
        HTTPException(404): If resident does not exist.
    """
    _ = current_admin

    resident = db.get(Resident, resident_id)
    if resident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resident not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Apply updates safely.
    for field, value in update_data.items():
        if field == "email" and value is not None:
            value = str(value)
        setattr(resident, field, value)

    db.add(resident)
    db.commit()
    db.refresh(resident)
    return resident


@router.delete(
    "/{resident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a resident",
    description="Delete a resident record by ID. Requires admin authentication.",
    operation_id="residents_delete",
)
def delete_resident(
    resident_id: int,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
) -> Response:
    """
    Delete a resident by ID.

    Args:
        resident_id: Resident ID.
        db: Database session dependency.
        current_admin: Authenticated admin (JWT bearer).

    Returns:
        Empty response with HTTP 204.

    Raises:
        HTTPException(404): If resident does not exist.
    """
    _ = current_admin

    resident = db.get(Resident, resident_id)
    if resident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resident not found")

    db.delete(resident)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
