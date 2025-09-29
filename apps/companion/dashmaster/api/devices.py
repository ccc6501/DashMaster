"""Device management endpoints."""
from __future__ import annotations

from asyncio import to_thread
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..core.events import bus
from ..models.devices import (
    DeviceBirthResponse,
    DeviceClaimRequest,
    DeviceClaimResponse,
    DeviceRef,
    DeviceReleaseResponse,
)
from ..store.database import SessionFactory
from ..store.models import Device

router = APIRouter(tags=["devices"])


@router.get("/devices", response_model=list[DeviceRef])
async def list_devices() -> list[DeviceRef]:
    """Return all devices ordered by slot index."""

    def _list() -> list[DeviceRef]:
        with SessionFactory() as session:
            devices = session.execute(select(Device).order_by(Device.slot_index)).scalars().all()
            return [
                DeviceRef(
                    hostname=device.hostname,
                    slot_index=device.slot_index,
                    http_port=device.http_port,
                    admin_port=device.admin_port,
                    mqtt_topic=device.mqtt_topic,
                    status=device.status,
                    profile=device.profile,
                    last_seen=device.last_seen,
                )
                for device in devices
            ]

    return await to_thread(_list)


@router.post("/devices/claim", response_model=DeviceClaimResponse)
async def claim_device(payload: DeviceClaimRequest) -> DeviceClaimResponse:
    """Claim the next available device slot."""

    def _claim() -> DeviceClaimResponse:
        with SessionFactory() as session:
            stmt = select(Device).order_by(Device.slot_index)
            devices = session.execute(stmt).scalars().all()
            target: Device | None = None
            if payload.requested_hostname:
                target = next(
                    (d for d in devices if d.hostname == payload.requested_hostname),
                    None,
                )
                if target is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Requested hostname not found",
                    )
                if target.status != "unclaimed":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Device already claimed",
                    )
            else:
                target = next((d for d in devices if d.status == "unclaimed"), None)
                if target is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="No available device slots",
                    )
            target.status = "claimed"
            target.profile = payload.profile
            target.updated_at = datetime.utcnow()
            session.add(target)
            session.commit()
            return DeviceClaimResponse(
                hostname=target.hostname,
                http_port=target.http_port,
                admin_port=target.admin_port,
                mqtt_topic=target.mqtt_topic,
                slot_index=target.slot_index,
            )

    response = await to_thread(_claim)
    await bus.publish(
        "device.claimed",
        {
            "hostname": response.hostname,
            "slot_index": response.slot_index,
            "profile": payload.profile,
        },
    )
    return response


@router.post("/devices/{hostname}/release", response_model=DeviceReleaseResponse)
async def release_device(hostname: str) -> DeviceReleaseResponse:
    """Release a claimed device slot."""

    def _release() -> DeviceReleaseResponse:
        with SessionFactory() as session:
            device = (
                session.execute(
                    select(Device).where(Device.hostname == hostname)
                ).scalars().first()
            )
            if device is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Device not found",
                )
            device.status = "unclaimed"
            device.profile = None
            device.updated_at = datetime.utcnow()
            session.add(device)
            session.commit()
            return DeviceReleaseResponse(hostname=hostname, status=device.status)

    response = await to_thread(_release)
    await bus.publish("device.released", {"hostname": hostname})
    return response


@router.get("/devices/{hostname}/birth", response_model=DeviceBirthResponse)
async def get_birth_certificate(hostname: str) -> DeviceBirthResponse:
    """Return stored birth JSON for a device."""

    def _load() -> DeviceBirthResponse:
        with SessionFactory() as session:
            device = (
                session.execute(
                    select(Device).where(Device.hostname == hostname)
                ).scalars().first()
            )
            if device is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Device not found",
                )
            if device.birth is None:
                return DeviceBirthResponse(hostname=hostname, birth={})
            return DeviceBirthResponse(hostname=hostname, birth=device.birth.json)

    return await to_thread(_load)
