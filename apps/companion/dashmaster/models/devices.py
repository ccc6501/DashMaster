"""Pydantic models for device APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceRef(BaseModel):
    hostname: str
    slot_index: int = Field(alias="slot_index")
    http_port: int
    admin_port: int
    mqtt_topic: str
    status: str
    profile: Optional[str] = None
    last_seen: Optional[datetime] = None

    class Config:
        populate_by_name = True


class DeviceClaimRequest(BaseModel):
    profile: Optional[str] = None
    requested_hostname: Optional[str] = None
    actor: Optional[str] = None


class DeviceClaimResponse(BaseModel):
    hostname: str
    http_port: int
    admin_port: int
    mqtt_topic: str
    slot_index: int


class DeviceReleaseResponse(BaseModel):
    hostname: str
    status: str


class DeviceBirthResponse(BaseModel):
    hostname: str
    birth: dict
