"""Seed the SQLite database from the reservations registry."""
from __future__ import annotations

from ..store.database import init_db, SessionFactory
from ..store.registry import seed_devices


def main() -> None:
    init_db()
    with SessionFactory() as session:
        seed_devices(session)
        session.commit()


if __name__ == "__main__":
    main()
