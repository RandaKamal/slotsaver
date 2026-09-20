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
    process (or a one-off script) was started from.

    Also normalises the `postgres://` scheme that hosted databases (including
    DigitalOcean managed Postgres) still hand out - SQLAlchemy 2.x only
    recognises `postgresql://` and raises NoSuchModuleError on the short form.
    """
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)

    prefix = "sqlite:///"
    if raw.startswith(prefix) and not raw.startswith(f"{prefix}/"):
        relative_path = raw.removeprefix(prefix)
        if not Path(relative_path).is_absolute():
            return f"{prefix}{_API_DIR / relative_path}"
    return raw


DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./relay.db"))

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# A managed Postgres sitting behind a connection pooler drops idle connections
# without telling us; pool_pre_ping turns the resulting stale-socket error into
# a transparent reconnect instead of a 500 on the first request after a lull.
engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
