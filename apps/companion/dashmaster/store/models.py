"""SQLAlchemy models for DashMaster companion storage."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class."""


class Device(Base):
    """Persistent record for a claimed device slot."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    http_port: Mapped[int] = mapped_column(Integer, nullable=False)
    admin_port: Mapped[int] = mapped_column(Integer, nullable=False)
    mqtt_topic: Mapped[str] = mapped_column(String(128), nullable=False)
    profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unclaimed", nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    birth: Mapped["DeviceBirth"] = relationship(
        back_populates="device", cascade="all, delete-orphan", uselist=False
    )
    configs: Mapped[list["ConfigHistory"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceBirth(Base):
    """Stored birth certificate JSON and hashes."""

    __tablename__ = "device_birth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped[Device] = relationship(back_populates="birth")


class ConfigHistory(Base):
    """Audit log for configuration uploads."""

    __tablename__ = "config_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    layout_sha: Mapped[Optional[str]] = mapped_column(String(64))
    rules_sha: Mapped[Optional[str]] = mapped_column(String(64))
    schema_sha: Mapped[Optional[str]] = mapped_column(String(64))
    config_sha: Mapped[Optional[str]] = mapped_column(String(64))
    calibration_sha: Mapped[Optional[str]] = mapped_column(String(64))
    board_map_sha: Mapped[Optional[str]] = mapped_column(String(64))
    theme_sha: Mapped[Optional[str]] = mapped_column(String(64))
    actor: Mapped[Optional[str]] = mapped_column(String(128))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device: Mapped[Device] = relationship(back_populates="configs")

    __table_args__ = (UniqueConstraint("device_id", "created_at", name="uq_config_history"),)
