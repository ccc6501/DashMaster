"""Serve JSON schema contracts."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["schema"])

_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "templates" / r"\$schema"


@router.get("/schema/contracts/{name}")
async def get_schema_contract(name: str) -> dict:
    path = _SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Schema not found")
    return json.loads(path.read_text(encoding="utf-8"))
