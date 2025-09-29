"""Database helpers for the companion service."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_DB_PATH = Path(__file__).resolve().parents[2] / "var" / "companion.db"


def ensure_db_dir() -> None:
    """Create parent directory for the SQLite database if needed."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


ensure_db_dir()

_ENGINE = create_engine(
    f"sqlite:///{_DB_PATH}", echo=False, future=True, connect_args={"check_same_thread": False}
)

SessionFactory = sessionmaker(bind=_ENGINE, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """Initialise tables if they do not exist."""
    Base.metadata.create_all(_ENGINE)


@asynccontextmanager
async def session_scope() -> AsyncIterator[Session]:
    """Provide an async context manager for DB sessions using thread executors."""

    from asyncio import get_running_loop

    session = SessionFactory()
    try:
        yield session
        await get_running_loop().run_in_executor(None, session.commit)
    except Exception:
        await get_running_loop().run_in_executor(None, session.rollback)
        raise
    finally:
        await get_running_loop().run_in_executor(None, session.close)


async def run_in_session(func: Callable[[Session], None]) -> None:
    """Utility to run blocking session work in a thread."""

    from asyncio import get_running_loop

    session = SessionFactory()
    try:
        await get_running_loop().run_in_executor(None, func, session)
    finally:
        session.close()
