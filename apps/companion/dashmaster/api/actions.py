"""Device action passthrough endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from ..core.http_client import create_device_client
from ..store.database import SessionFactory
from ..store.models import Device

router = APIRouter(tags=["devices"])


def _get_device_ports(hostname: str) -> int:
    with SessionFactory() as session:
        device = (
            session.execute(
                select(Device).where(Device.hostname == hostname)
            ).scalars().first()
        )
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
        return device.http_port


async def _perform_action(hostname: str, path: str, *, params: dict | None = None) -> dict[str, str]:
    http_port = _get_device_ports(hostname)
    async with create_device_client(hostname=hostname, http_port=http_port) as client:
        response = await client.post(path, params=params or {})
        if response.is_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Device responded with {response.status_code}"
            )
    return {"hostname": hostname, "action": path}


def _ensure_flags(request: Request) -> None:
    flags = getattr(request.app.state, "flags", None)
    if flags is not None:
        flags.ensure_ntp_ready()


@router.post("/devices/{hostname}/identify")
async def identify_device(
    request: Request,
    hostname: str,
    minutes: int = Query(5, ge=1, le=10),
) -> dict[str, str]:
    _ensure_flags(request)
    return await _perform_action(hostname, "/api/identify", params={"minutes": minutes})


@router.post("/devices/{hostname}/reboot")
async def reboot_device(request: Request, hostname: str) -> dict[str, str]:
    _ensure_flags(request)
    return await _perform_action(hostname, "/api/reboot")


@router.post("/devices/{hostname}/factory_reset")
async def factory_reset_device(request: Request, hostname: str) -> dict[str, str]:
    _ensure_flags(request)
    return await _perform_action(hostname, "/api/factory_reset")
