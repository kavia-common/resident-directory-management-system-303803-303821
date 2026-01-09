import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.auth import router as auth_router
from src.api.routes.residents import router as residents_router
from src.db.session import get_engine

openapi_tags = [
    {"name": "health", "description": "Service health and basic diagnostics."},
    {"name": "auth", "description": "Admin authentication (JWT bearer)."},
    {"name": "residents", "description": "Resident directory management (CRUD + search)."},
]


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with a default."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    return value


def _get_cors_allowed_origins() -> List[str]:
    """
    Build the allow_origins list for CORSMiddleware.

    Sources (in priority order):
      1) CORS_ALLOWED_ORIGINS env var, comma-separated
      2) FRONTEND_PREVIEW_URL env var (if present)
      3) defaults: http://localhost:3000

    Notes:
      - We keep defaults minimal and do NOT allow '*' with credentials.
      - If you need multiple preview URLs, put them in CORS_ALLOWED_ORIGINS.
    """
    # 1) Comma-separated list
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    origins: List[str] = []
    if raw:
        origins.extend([o.strip() for o in raw.split(",") if o and o.strip()])

    # 2) Optional single preview URL (some preview systems provide this)
    preview = (os.getenv("FRONTEND_PREVIEW_URL") or "").strip()
    if preview:
        origins.append(preview)

    # 3) Sensible dev default
    if not origins:
        origins = ["http://localhost:3000"]

    # Normalize: drop trailing slashes and de-dupe while preserving order
    normalized: List[str] = []
    seen = set()
    for o in origins:
        v = o.rstrip("/")
        if v and v not in seen:
            seen.add(v)
            normalized.append(v)
    return normalized


def _get_database_url_for_docs() -> Optional[str]:
    """Return DATABASE_URL if present (redacted for docs)."""
    url = (os.getenv("DATABASE_URL") or "").strip()
    return "***set***" if url else None


app = FastAPI(
    title="Resident Directory Backend API",
    description=(
        "Backend API for managing a resident directory (residents CRUD) and admin authentication.\n\n"
        "Environment:\n"
        "- DATABASE_URL (required): PostgreSQL connection string.\n"
        "- JWT_SECRET_KEY (required): Secret used to sign JWT tokens.\n"
        "- JWT_ALGORITHM (optional): JWT algorithm (default: HS256).\n"
        "- ACCESS_TOKEN_EXPIRE_MINUTES (optional): Access token TTL in minutes (default: 60).\n"
        "- CORS_ALLOWED_ORIGINS (optional): Comma-separated list of allowed frontend origins.\n"
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# CORS: allow configured frontend origins; do not default to "*" when credentials are enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)
app.include_router(residents_router)


@app.on_event("startup")
def _startup_check_config() -> None:
    """
    Validate required configuration early on startup.

    Raises:
        RuntimeError: If DATABASE_URL is missing/invalid.
    """
    # Ensure env var is present and that an engine can be constructed.
    # get_engine() will raise a clear RuntimeError if DATABASE_URL is missing.
    get_engine(os.getenv("DATABASE_URL"))

    # ACCESS_TOKEN_EXPIRE_MINUTES is optional but we validate if set.
    _ = _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)


@app.get("/", tags=["health"], summary="Health check")
def health_check():
    """Return a simple health response."""
    return {"message": "Healthy"}


@app.get(
    "/config/health",
    tags=["health"],
    summary="Config health (env + CORS)",
    description=(
        "Lightweight diagnostics endpoint to verify configuration is loaded.\n\n"
        "Returns:\n"
        "- Whether required env vars appear set\n"
        "- The resolved CORS allowed origins\n"
        "- Token expiry minutes (resolved)\n"
    ),
    operation_id="config_health",
)
def config_health():
    """Return a small diagnostics payload (no secrets)."""
    return {
        "env": {
            "DATABASE_URL": _get_database_url_for_docs(),
            "JWT_SECRET_KEY": "***set***" if (os.getenv("JWT_SECRET_KEY") or "").strip() else None,
            "JWT_ALGORITHM": (os.getenv("JWT_ALGORITHM") or "HS256").strip(),
            "ACCESS_TOKEN_EXPIRE_MINUTES": _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        },
        "cors": {"allowed_origins": _get_cors_allowed_origins()},
    }
