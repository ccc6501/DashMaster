"""Config upload endpoint."""
from __future__ import annotations

import json
from asyncio import to_thread
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from ..core.events import bus
from ..store.database import SessionFactory
from ..store.models import ConfigHistory, Device, DeviceBirth
from ..util.hashing import sha256_bytes
from ..util.schema import SchemaValidationError, validate

router = APIRouter(tags=["upload"])

_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "var" / "device_storage"


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


def _ensure_storage_dir(hostname: str) -> Path:
    target = _STORAGE_ROOT / hostname
    target.mkdir(parents=True, exist_ok=True)
    return target


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

    storage_dir = await to_thread(_ensure_storage_dir, hostname)

    await to_thread(
        _write_files,
        storage_dir,
        {
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
            **(
                {"theme.css": theme_text.encode("utf-8")}
                if theme_text is not None
                else {}
            ),
        },
    )

    def _record() -> dict[str, Any]:
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
                layout_sha=layout_sha,
                rules_sha=rules_sha,
                schema_sha=schema_sha,
                calibration_sha=calibration_sha,
                board_map_sha=board_map_sha,
                theme_sha=theme_sha,
                actor=actor,
            )
            session.add(history)

            birth = (
                session.execute(
                    select(DeviceBirth).where(DeviceBirth.device_id == device.id)
                ).scalars().first()
            )
            if birth is None:
                birth = DeviceBirth(
                    device_id=device.id,
                    json={"device_id": hostname, "configs": {}},
                )
                session.add(birth)

            configs = dict(birth.json.get("configs", {}))
            configs.update(
                {
                    "layout": layout_sha,
                    "rules": rules_sha,
                    **({"schema": schema_sha} if schema_sha else {}),
                    **({"calibration": calibration_sha} if calibration_sha else {}),
                    **({"board_map": board_map_sha} if board_map_sha else {}),
                    **({"theme": theme_sha} if theme_sha else {}),
                }
            )
            birth_json = dict(birth.json)
            birth_json["configs"] = configs
            birth.json = birth_json
            session.add(birth)
            session.commit()
            return {
                "device": hostname,
                "hashes": {
                    "layout": layout_sha,
                    "rules": rules_sha,
                    "schema": schema_sha,
                    "calibration": calibration_sha,
                    "board_map": board_map_sha,
                    "theme": theme_sha,
                },
            }

    result = await to_thread(_record)
    await bus.publish("config.uploaded", {"hostname": hostname, **result["hashes"]})
    return result


def _write_files(target: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        (target / name).write_bytes(content)
