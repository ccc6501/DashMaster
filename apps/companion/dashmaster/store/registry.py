"""Registry import helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device

_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "reservations" / "registry.json"


def load_registry() -> dict:
    """Load the canonical registry JSON."""
    with _REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def seed_devices(session: Session) -> None:
    """Insert registry devices that are not yet present in the DB."""
    registry = load_registry()
    existing = {
        device.hostname
        for device in session.execute(select(Device)).scalars().all()
    }
    for entry in _iter_devices(registry):
        if entry["hostname"] in existing:
            continue
        session.add(
            Device(
                hostname=entry["hostname"],
                slot_index=entry["slot_index"],
                http_port=entry["http_port"],
                admin_port=entry["admin_port"],
                mqtt_topic=entry["mqtt_topic"],
                status="unclaimed",
            )
        )


def _iter_devices(data: dict) -> Iterable[dict]:
    yield from data.get("devices", [])
