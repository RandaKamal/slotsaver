"""SQLAlchemy engine/session setup, driven by DATABASE_URL."""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# apps/api/app/db/session.py -> apps/api
_API_DIR = Path(__file__).resolve().parents[2]


def _resolve_database_url(raw: str) -> str:
    """Anchors a relative sqlite path to apps/api, so the DB file is always
    in the same place (apps/api/relay.db) regardless of which directory the
    process (or a one-off script) was started from."""
    prefix = "sqlite:///"
    if raw.startswith(prefix) and not raw.startswith(f"{prefix}/"):
        relative_path = raw.removeprefix(prefix)
        if not Path(relative_path).is_absolute():
            return f"{prefix}{_API_DIR / relative_path}"
    return raw


DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./relay.db"))

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
