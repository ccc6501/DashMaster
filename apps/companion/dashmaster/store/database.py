"""Database helpers for the companion service."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "var" / "companion.db"


def _resolve_engine() -> Engine:
    url = os.getenv("DASHMASTER_DB_URL")
    if url:
        return create_engine(url, echo=False, future=True)

    sqlite_path = Path(os.getenv("DASHMASTER_DB_PATH", str(_DEFAULT_DB_PATH)))
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{sqlite_path}",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )


ENGINE = _resolve_engine()

SessionFactory = sessionmaker(bind=ENGINE, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """Initialise tables if they do not exist."""
    Base.metadata.create_all(ENGINE)


def reset_engine() -> None:
    """Recreate the SQLAlchemy engine from environment configuration."""

    global ENGINE, SessionFactory
    ENGINE.dispose()
    ENGINE = _resolve_engine()
    SessionFactory.configure(bind=ENGINE)
    Base.metadata.create_all(ENGINE)


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
