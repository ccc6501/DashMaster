"""Config upload endpoint."""
from __future__ import annotations

import json
import shutil
from asyncio import to_thread
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from pydantic import BaseModel

from ..core.events import bus
from ..core.http_client import create_device_client
from ..store.database import SessionFactory
from ..store.models import ConfigHistory, Device, DeviceBirth
from ..util.hashing import sha256_bytes
from ..util.schema import SchemaValidationError, validate
from ..util.storage import device_storage_dir, iter_snapshots

router = APIRouter(tags=["upload"])

_ARTIFACT_ENDPOINTS: dict[str, tuple[str, str]] = {
    "layout.json": ("/api/layout", "application/json"),
    "rules.json": ("/api/rules", "application/json"),
    "schema.json": ("/api/schema", "application/json"),
    "calibration.json": ("/api/calibration", "application/json"),
    "board_map.json": ("/api/board_map", "application/json"),
    "theme.css": ("/api/theme", "text/css"),
}

_CONFIG_HASH_KEYS: dict[str, str] = {
    "layout.json": "layout",
    "rules.json": "rules",
    "schema.json": "schema",
    "calibration.json": "calibration",
    "board_map.json": "board_map",
    "theme.css": "theme",
}

_CONFIG_KEYS = ["layout", "rules", "schema", "calibration", "board_map", "theme"]


@dataclass(slots=True)
class Artifact:
    """Payload destined for a device endpoint."""

    filename: str
    endpoint: str
    content: bytes
    content_type: str


class RollbackRequest(BaseModel):
    """Payload for triggering a rollback."""

    snapshot: str | None = None
    actor: str | None = None


class RollbackSnapshot(BaseModel):
    """Snapshot metadata returned to clients."""

    name: str
    created_at: datetime
    files: list[str]
    hashes: dict[str, str | None]


class RollbackResponse(BaseModel):
    """Response returned after completing a rollback."""

    device: str
    rollback: str
    hashes: dict[str, str | None]
    diff: dict[str, bool]


async def _read_json(file: UploadFile, *, schema_name: str) -> tuple[dict[str, Any], str]:
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file.filename or schema_name} is not valid JSON: {exc}",
        ) from exc
    try:
        validate(data, schema_name=schema_name)
    except SchemaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file.filename or schema_name} failed validation at {exc.path}: {exc}",
        ) from exc
    digest = sha256_bytes(raw)
    return data, digest


async def _read_text(file: UploadFile) -> tuple[str, str]:
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file.filename or 'theme'} must be UTF-8 text",
        ) from exc
    digest = sha256_bytes(raw)
    return text, digest

@router.post("/upload/{hostname}")
async def upload_config_pack(
    hostname: str,
    layout: UploadFile = File(...),
    rules: UploadFile = File(...),
    schema: UploadFile | None = File(None),
    calibration: UploadFile | None = File(None),
    board_map: UploadFile | None = File(None),
    theme: UploadFile | None = File(None),
    actor: str | None = Form(None),
) -> dict[str, Any]:
    """Validate and persist a config pack for a device."""

    layout_json, layout_sha = await _read_json(layout, schema_name="layout")
    rules_json, rules_sha = await _read_json(rules, schema_name="rules")

    for idx, actuator in enumerate(rules_json.get("actuators", [])):
        if "ttl_s" not in actuator or "cooldown_s" not in actuator:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Actuator entry {idx} missing ttl_s/cooldown_s",
            )

    schema_json: dict[str, Any] | None = None
    schema_sha: str | None = None
    if schema is not None:
        schema_json, schema_sha = await _read_json(schema, schema_name="schema")

    calibration_json: dict[str, Any] | None = None
    calibration_sha: str | None = None
    if calibration is not None:
        calibration_json, calibration_sha = await _read_json(calibration, schema_name="calibration")

    board_map_json: dict[str, Any] | None = None
    board_map_sha: str | None = None
    if board_map is not None:
        board_map_json, board_map_sha = await _read_json(board_map, schema_name="board_map")

    theme_text: str | None = None
    theme_sha: str | None = None
    if theme is not None:
        theme_text, theme_sha = await _read_text(theme)

    device_info = await to_thread(_get_device_info, hostname)

    storage_dir = await to_thread(device_storage_dir, hostname)
    previous_hashes = await to_thread(_collect_hashes_from_storage, storage_dir)

    files_to_write: dict[str, bytes] = {
        "layout.json": json.dumps(layout_json, indent=2).encode("utf-8"),
        "rules.json": json.dumps(rules_json, indent=2).encode("utf-8"),
        **(
            {"schema.json": json.dumps(schema_json, indent=2).encode("utf-8")}
            if schema_json is not None
            else {}
        ),
        **(
            {"calibration.json": json.dumps(calibration_json, indent=2).encode("utf-8")}
            if calibration_json is not None
            else {}
        ),
        **(
            {"board_map.json": json.dumps(board_map_json, indent=2).encode("utf-8")}
            if board_map_json is not None
            else {}
        ),
        **({"theme.css": theme_text.encode("utf-8")} if theme_text is not None else {}),
    }

    artifacts = _prepare_artifacts(files_to_write)

    await _push_to_device(
        hostname,
        device_info["http_port"],
        artifacts,
    )

    snapshot_label = await to_thread(
        _snapshot_previous_pack,
        storage_dir,
        set(files_to_write.keys()),
    )

    storage_dir = await to_thread(device_storage_dir, hostname)

    await to_thread(
        _write_files,
        storage_dir,
        files_to_write,
    )

    hashes = {
        "layout": layout_sha,
        "rules": rules_sha,
        "schema": schema_sha,
        "calibration": calibration_sha,
        "board_map": board_map_sha,
        "theme": theme_sha,
    }
    diff = _compute_diff(previous_hashes, hashes)

    result = await to_thread(
        _record_history_and_birth,
        hostname,
        hashes,
        actor,
        json.dumps({"rollback": snapshot_label}) if snapshot_label else None,
    )
    payload = {
        "hostname": hostname,
        "hashes": hashes,
        "diff": diff,
        "snapshot": snapshot_label,
        "actor": actor,
    }
    await bus.publish("config.uploaded", payload)
    return {**result, "diff": diff, "snapshot": snapshot_label}


def _write_files(target: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        (target / name).write_bytes(content)


def _get_device_info(hostname: str) -> dict[str, Any]:
    with SessionFactory() as session:
        device = (
            session.execute(select(Device).where(Device.hostname == hostname)).scalars().first()
        )
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found",
            )
        return {"id": device.id, "http_port": device.http_port}


def _snapshot_previous_pack(target: Path, filenames: set[str]) -> str | None:
    existing = [name for name in filenames if (target / name).exists()]
    if not existing:
        return None

    history_dir = target / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_dir = history_dir / timestamp
    snapshot_dir.mkdir(exist_ok=True)
    for name in existing:
        src = target / name
        shutil.copy2(src, snapshot_dir / name)
    return snapshot_dir.name


def _prepare_artifacts(files: dict[str, bytes]) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for filename, content in files.items():
        mapping = _ARTIFACT_ENDPOINTS.get(filename)
        if mapping is None:
            continue
        endpoint, content_type = mapping
        artifacts.append(Artifact(filename, endpoint, content, content_type))
    return artifacts


async def _push_to_device(hostname: str, http_port: int, artifacts: Iterable[Artifact]) -> None:
    try:
        async with create_device_client(hostname=hostname, http_port=http_port) as client:
            for artifact in artifacts:
                response = await client.post_bytes(
                    artifact.endpoint,
                    artifact.content,
                    artifact.content_type,
                )
                if response.is_error:
                    detail = response.text.strip() or response.reason_phrase or "Device error"
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            f"Device responded with {response.status_code} at "
                            f"{artifact.endpoint}: {detail}"
                        ),
                    )
    except httpx.HTTPError as exc:  # pragma: no cover - network failure
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach device {hostname}: {exc}",
        ) from exc


def _record_history_and_birth(
    hostname: str,
    hashes: dict[str, str | None],
    actor: str | None,
    note: str | None,
) -> dict[str, Any]:
    with SessionFactory() as session:
        device = (
            session.execute(select(Device).where(Device.hostname == hostname)).scalars().first()
        )
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found",
            )

        history = ConfigHistory(
            device_id=device.id,
            layout_sha=hashes.get("layout"),
            rules_sha=hashes.get("rules"),
            schema_sha=hashes.get("schema"),
            calibration_sha=hashes.get("calibration"),
            board_map_sha=hashes.get("board_map"),
            theme_sha=hashes.get("theme"),
            actor=actor,
            note=note,
        )
        session.add(history)

        birth = (
            session.execute(select(DeviceBirth).where(DeviceBirth.device_id == device.id))
            .scalars()
            .first()
        )
        if birth is None:
            birth = DeviceBirth(
                device_id=device.id,
                json={"device_id": hostname, "configs": {}},
            )
            session.add(birth)

        configs = dict(birth.json.get("configs", {}))
        for filename, key in _CONFIG_HASH_KEYS.items():
            value = hashes.get(key)
            if value is not None:
                configs[key] = value

        birth_json = dict(birth.json)
        birth_json["configs"] = configs
        birth.json = birth_json
        birth.sha256 = sha256_bytes(json.dumps(birth_json, sort_keys=True).encode("utf-8"))
        session.add(birth)
        session.commit()
        return {"device": hostname, "hashes": hashes}


def _collect_hashes_from_files(files: dict[str, bytes]) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {key: None for key in _CONFIG_KEYS}
    for filename, content in files.items():
        key = _CONFIG_HASH_KEYS.get(filename)
        if key is not None:
            hashes[key] = sha256_bytes(content)
    return hashes


def _collect_hashes_from_storage(storage_dir: Path) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {key: None for key in _CONFIG_KEYS}
    for filename, key in _CONFIG_HASH_KEYS.items():
        path = storage_dir / filename
        if path.exists():
            hashes[key] = sha256_bytes(path.read_bytes())
    return hashes


def _compute_diff(
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> dict[str, bool]:
    return {key: previous.get(key) != current.get(key) for key in _CONFIG_KEYS}


def _load_snapshot_files(snapshot_dir: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in snapshot_dir.iterdir():
        if path.is_file():
            files[path.name] = path.read_bytes()
    return files


def _overwrite_storage_from_snapshot(storage_dir: Path, files: dict[str, bytes]) -> None:
    for filename in _ARTIFACT_ENDPOINTS.keys():
        target = storage_dir / filename
        if filename not in files and target.exists():
            target.unlink()
    for filename, content in files.items():
        (storage_dir / filename).write_bytes(content)


def _gather_snapshots(storage_dir: Path) -> list[RollbackSnapshot]:
    history_dir = storage_dir / "history"
    if not history_dir.exists():
        return []
    snapshots: list[RollbackSnapshot] = []
    for path in sorted([p for p in history_dir.iterdir() if p.is_dir()]):
        files = _load_snapshot_files(path)
        hashes = _collect_hashes_from_files(files)
        created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        snapshots.append(
            RollbackSnapshot(
                name=path.name,
                created_at=created_at,
                files=sorted(files.keys()),
                hashes=hashes,
            )
        )
    return snapshots


@router.post("/upload/{hostname}/rollback", response_model=RollbackResponse)
async def rollback_config_pack(
    hostname: str,
    payload: RollbackRequest | None = None,
) -> RollbackResponse:
    """Restore the device configuration from a stored snapshot."""

    payload = payload or RollbackRequest()

    storage_dir = await to_thread(device_storage_dir, hostname)
    history_dir = storage_dir / "history"
    if not history_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No rollback snapshots available",
        )

    available = sorted([path for path in history_dir.iterdir() if path.is_dir()])
    if not available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No rollback snapshots available",
        )

    previous_hashes = await to_thread(_collect_hashes_from_storage, storage_dir)

    snapshot_dir: Path
    if payload.snapshot:
        snapshot_dir = history_dir / payload.snapshot
        if not snapshot_dir.exists() or not snapshot_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Snapshot {payload.snapshot} not found",
            )
    else:
        snapshot_dir = available[-1]

    snapshot_files = await to_thread(_load_snapshot_files, snapshot_dir)
    if not snapshot_files:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Snapshot is empty",
        )

    device_info = await to_thread(_get_device_info, hostname)

    artifacts = _prepare_artifacts(snapshot_files)
    await _push_to_device(hostname, device_info["http_port"], artifacts)

    await to_thread(
        _snapshot_previous_pack,
        storage_dir,
        set(snapshot_files.keys()),
    )

    await to_thread(_overwrite_storage_from_snapshot, storage_dir, snapshot_files)

    hashes = await to_thread(_collect_hashes_from_files, snapshot_files)
    diff = _compute_diff(previous_hashes, hashes)

    result = await to_thread(
        _record_history_and_birth,
        hostname,
        hashes,
        payload.actor,
        json.dumps({"rolled_back_to": snapshot_dir.name}),
    )

    await bus.publish(
        "config.rollback",
        {
            "hostname": hostname,
            "snapshot": snapshot_dir.name,
            "hashes": hashes,
            "diff": diff,
            "actor": payload.actor,
        },
    )
    return RollbackResponse(
        device=result["device"],
        rollback=snapshot_dir.name,
        hashes=result["hashes"],
        diff=diff,
    )


@router.get("/upload/{hostname}/snapshots", response_model=list[RollbackSnapshot])
async def list_snapshots(hostname: str) -> list[RollbackSnapshot]:
    """Return available rollback snapshots for a device."""

    storage_dir = await to_thread(device_storage_dir, hostname)
    return await to_thread(_gather_snapshots, storage_dir)
