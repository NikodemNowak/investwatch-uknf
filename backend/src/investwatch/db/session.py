"""Engine and session factories."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from investwatch.config import get_settings


@cache
def get_engine() -> Engine:
    """Return the process-wide engine for the configured database."""
    url = get_settings().sqlalchemy_url
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


@cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the session factory bound to the engine."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session that commits on success and rolls back on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with session_scope() as session:
        yield session
