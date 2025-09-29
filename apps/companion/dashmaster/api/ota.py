"""OTA stubs for Phase 1."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ota"])


@router.post("/ota/{hostname}")
async def initiate_ota(hostname: str) -> dict[str, str]:
    """Placeholder OTA endpoint returning a not-implemented response."""

    raise HTTPException(status_code=501, detail="OTA support arrives in Phase 2")
