"""
Database engine and session management.

Uses SQLAlchemy 2.0 style. SQLite is the default (zero-config, file-based,
correct choice for a single-user desktop app); swapping to Postgres is a
one-line env var change (see core/config.py) with no code changes required
since we never use SQLite-specific SQL.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.core.config import get_settings

settings = get_settings()

# Ensure the SQLite data directory exists before the engine tries to open it.
if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context-manager version for use outside of FastAPI request handlers
    (e.g. background sensing loops, the decision engine)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called once on app startup. For real migrations
    as the schema evolves, use Alembic (already in requirements.txt)."""
    from app.models import user, state, action, feedback  # noqa: F401 (register models)
    Base.metadata.create_all(bind=engine)
