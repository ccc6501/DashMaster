"""Device storage helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


_DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "var" / "device_storage"


def storage_root() -> Path:
    return Path(os.getenv("DASHMASTER_STORAGE_ROOT", str(_DEFAULT_STORAGE_ROOT)))


def device_storage_dir(hostname: str) -> Path:
    target = storage_root() / hostname
    target.mkdir(parents=True, exist_ok=True)
    return target


def snapshots_dir(hostname: str) -> Path:
    return device_storage_dir(hostname) / "history"


def iter_snapshots(hostname: str) -> Iterable[Path]:
    directory = snapshots_dir(hostname)
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir())
