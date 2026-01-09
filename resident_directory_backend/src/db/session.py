import os
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _get_database_url() -> str:
    """
    Read DATABASE_URL from environment.

    Raises:
        RuntimeError: If DATABASE_URL is missing/blank.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url or not database_url.strip():
        raise RuntimeError(
            "DATABASE_URL environment variable is required but was not set. "
            "Set DATABASE_URL to a PostgreSQL connection string, e.g. "
            "'postgresql://user:password@host:5432/dbname'."
        )
    return database_url.strip()


def get_engine(database_url: Optional[str] = None) -> Engine:
    """
    Create a SQLAlchemy Engine for the given database_url (or env DATABASE_URL).

    Notes:
        - Uses pool_pre_ping to reduce stale connection issues.
        - For Postgres, DATABASE_URL should start with 'postgresql://'.
    """
    url = database_url or _get_database_url()
    return create_engine(url, pool_pre_ping=True)


# Create a module-level engine/sessionmaker to be reused across requests.
_ENGINE: Engine = get_engine()
_SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session.

    Yields:
        sqlalchemy.orm.Session: A session bound to the configured engine.

    Ensures:
        The session is closed after the request finishes.
    """
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
