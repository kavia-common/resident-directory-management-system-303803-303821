import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.session import get_engine

openapi_tags = [
    {"name": "health", "description": "Service health and basic diagnostics."},
]

app = FastAPI(
    title="Resident Directory Backend API",
    description=(
        "Backend API for managing a resident directory (residents CRUD) and admin authentication.\n\n"
        "Environment:\n"
        "- DATABASE_URL (required): PostgreSQL connection string."
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_check_db_config() -> None:
    """
    Validate DB configuration early on startup.

    Raises:
        RuntimeError: If DATABASE_URL is missing/invalid.
    """
    # Ensure env var is present and that an engine can be constructed.
    # get_engine() will raise a clear RuntimeError if DATABASE_URL is missing.
    get_engine(os.getenv("DATABASE_URL"))


@app.get("/", tags=["health"], summary="Health check")
def health_check():
    """Return a simple health response."""
    return {"message": "Healthy"}
