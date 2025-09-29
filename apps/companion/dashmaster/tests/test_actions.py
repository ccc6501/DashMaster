"""Tests for device action passthrough endpoints and schema serving."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from ..core.http_client import DeviceClient
from ..main import app
from .device_emulator import ACTION_LOG, app as emulator_app, reset_actions


@pytest.fixture(autouse=True)
def _reset_actions():
    reset_actions()


@pytest.fixture(autouse=True)
def patch_device_client(monkeypatch: pytest.MonkeyPatch):

    @asynccontextmanager
    async def _factory(*, hostname: str, http_port: int, transport=None):
        client = DeviceClient(
            "http://device-emulator",
            transport=transport or httpx.ASGITransport(app=emulator_app),
        )
        try:
            yield client
        finally:
            await client.close()

    monkeypatch.setattr(
        "apps.companion.dashmaster.api.actions.create_device_client",
        _factory,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_identify_action(client: TestClient) -> None:
    response = client.post("/api/devices/esp-000/identify", params={"minutes": 7})
    assert response.status_code == 200
    assert ACTION_LOG[-1] == ("identify", {"minutes": 7})


def test_reboot_action(client: TestClient) -> None:
    response = client.post("/api/devices/esp-000/reboot")
    assert response.status_code == 200
    assert ACTION_LOG[-1][0] == "reboot"


def test_factory_reset_action(client: TestClient) -> None:
    response = client.post("/api/devices/esp-000/factory_reset")
    assert response.status_code == 200
    assert ACTION_LOG[-1][0] == "factory_reset"


def test_schema_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/schema/contracts/layout")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "object"
