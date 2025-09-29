"""Integration tests for the upload workflow."""
from __future__ import annotations

import json
import os
import shutil
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Configure isolated storage paths for tests before importing the app module.
_TEST_VAR_ROOT = Path(__file__).resolve().parent / "_tmp_var"
os.environ.setdefault("DASHMASTER_STORAGE_ROOT", str((_TEST_VAR_ROOT / "device_storage").resolve()))
os.environ.setdefault("DASHMASTER_DB_PATH", str((_TEST_VAR_ROOT / "companion.db").resolve()))

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select

from ..core.events import bus
from ..core.http_client import DeviceClient
from ..main import app
from ..store.database import ENGINE, SessionFactory, reset_engine
from ..store.models import ConfigHistory, DeviceBirth
from .device_emulator import ACTION_LOG, app as emulator_app, reset_actions

VAR_ROOT = Path(os.environ["DASHMASTER_STORAGE_ROOT"]).parent
STORAGE_DIR = Path(os.environ["DASHMASTER_STORAGE_ROOT"])
DB_PATH = Path(os.environ["DASHMASTER_DB_PATH"])
EMU_STORAGE = Path(__file__).parent / "_emu_storage"
TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "templates"


@pytest.fixture(autouse=True)
def reset_state() -> None:
    ENGINE.dispose()
    if VAR_ROOT.exists():
        shutil.rmtree(VAR_ROOT)
    if EMU_STORAGE.exists():
        shutil.rmtree(EMU_STORAGE)
    if DB_PATH.exists():
        DB_PATH.unlink()
    reset_engine()
    EMU_STORAGE.mkdir(parents=True, exist_ok=True)
    VAR_ROOT.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    reset_actions()


@pytest.fixture(autouse=True)
def patch_device_client(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def _factory(*, hostname: str, http_port: int, transport: httpx.BaseTransport | None = None):
        client = DeviceClient(
            "http://device-emulator",
            transport=transport or httpx.ASGITransport(app=emulator_app),
        )
        try:
            yield client
        finally:
            await client.close()

    monkeypatch.setattr(
        "apps.companion.dashmaster.api.upload.create_device_client",
        _factory,
    )
    monkeypatch.setattr(
        "apps.companion.dashmaster.api.actions.create_device_client",
        _factory,
    )


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch):
    events: list[tuple[str, dict[str, object]]] = []
    original_publish = bus.publish

    async def capture(event_type: str, payload: dict[str, object]) -> None:
        events.append((event_type, payload))
        await original_publish(event_type, payload)

    monkeypatch.setattr(bus, "publish", capture)
    return events


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _load_template(name: str) -> dict[str, object]:
    return json.loads((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def test_upload_happy_path(client: TestClient, captured_events) -> None:
    layout = _load_template("layout.json")
    rules = _load_template("rules.json")

    response = client.post(
        "/api/upload/esp-000",
        data={"actor": "tester"},
        files={
            "layout": ("layout.json", json.dumps(layout), "application/json"),
            "rules": ("rules.json", json.dumps(rules), "application/json"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["device"] == "esp-000"
    assert set(payload["hashes"].keys()) == {"layout", "rules", "schema", "calibration", "board_map", "theme"}
    assert payload["snapshot"] is None
    assert payload["diff"]["layout"] is True
    assert payload["diff"]["rules"] is True

    device_storage = STORAGE_DIR / "esp-000"
    assert json.loads((device_storage / "layout.json").read_text(encoding="utf-8")) == layout
    assert json.loads((device_storage / "rules.json").read_text(encoding="utf-8")) == rules
    assert (EMU_STORAGE / "layout.json").exists()
    assert (EMU_STORAGE / "rules.json").exists()

    with SessionFactory() as session:
        history = session.execute(select(ConfigHistory)).scalars().all()
        assert len(history) == 1
        entry = history[0]
        assert entry.actor == "tester"
        assert entry.layout_sha == payload["hashes"]["layout"]
        birth = session.execute(select(DeviceBirth)).scalars().one()
        assert birth.json["configs"]["layout"] == payload["hashes"]["layout"]
        assert len(birth.sha256) == 64

    assert len(captured_events) == 1
    event_type, event_payload = captured_events[0]
    assert event_type == "config.uploaded"
    assert event_payload["hostname"] == "esp-000"
    assert event_payload["hashes"]["layout"] == payload["hashes"]["layout"]
    assert event_payload["diff"]["layout"] is True
    assert event_payload["snapshot"] is None
    assert event_payload["actor"] == "tester"

    devices_response = client.get("/api/devices")
    device_entries = devices_response.json()
    entry = next(item for item in device_entries if item["hostname"] == "esp-000")
    assert entry["hashes"]["layout"] == payload["hashes"]["layout"]
    assert entry["snapshots"] == []


def test_upload_rejects_missing_ttl(client: TestClient) -> None:
    layout = _load_template("layout.json")
    rules = {
        "version": "1.0",
        "actuators": [
            {"id": "pump-001", "cooldown_s": 10},
        ],
    }

    response = client.post(
        "/api/upload/esp-000",
        files={
            "layout": ("layout.json", json.dumps(layout), "application/json"),
            "rules": ("rules.json", json.dumps(rules), "application/json"),
        },
    )
    assert response.status_code == 400
    assert "ttl" in response.json()["detail"].lower()


def test_rollback_restores_previous_snapshot(client: TestClient, captured_events) -> None:
    layout_first = {
        "version": "1.0",
        "widgets": ["initial"],
    }
    rules_first = {
        "version": "1.0",
        "actuators": [],
    }
    layout_second = {
        "version": "1.0",
        "widgets": ["updated"],
    }
    rules_second = {
        "version": "1.0",
        "actuators": [
            {
                "id": "fan-1",
                "ttl_s": 5,
                "cooldown_s": 10,
            }
        ],
    }

    for layout, rules in ((layout_first, rules_first), (layout_second, rules_second)):
        response = client.post(
            "/api/upload/esp-000",
            files={
                "layout": ("layout.json", json.dumps(layout), "application/json"),
                "rules": ("rules.json", json.dumps(rules), "application/json"),
            },
        )
        assert response.status_code == 200

    history_dir = STORAGE_DIR / "esp-000" / "history"
    snapshots = sorted(history_dir.iterdir())
    assert len(snapshots) == 1
    snapshot_layout = json.loads((snapshots[0] / "layout.json").read_text(encoding="utf-8"))
    assert snapshot_layout == layout_first

    list_response = client.get("/api/upload/esp-000/snapshots")
    assert list_response.status_code == 200
    listing = list_response.json()
    assert len(listing) == 1
    assert listing[0]["name"] == snapshots[0].name
    assert "layout.json" in listing[0]["files"]
    assert listing[0]["hashes"]["layout"] is not None

    rollback = client.post(
        "/api/upload/esp-000/rollback",
        json={"actor": "operator"},
    )
    assert rollback.status_code == 200
    rollback_payload = rollback.json()
    assert rollback_payload["device"] == "esp-000"
    assert rollback_payload["rollback"] == snapshots[0].name
    assert rollback_payload["diff"]["layout"] is True

    device_storage = STORAGE_DIR / "esp-000"
    restored_layout = json.loads((device_storage / "layout.json").read_text(encoding="utf-8"))
    assert restored_layout == layout_first
    restored_rules = json.loads((device_storage / "rules.json").read_text(encoding="utf-8"))
    assert restored_rules == rules_first
    emulator_layout = json.loads((EMU_STORAGE / "layout.json").read_text(encoding="utf-8"))
    assert emulator_layout == layout_first
    emulator_rules = json.loads((EMU_STORAGE / "rules.json").read_text(encoding="utf-8"))
    assert emulator_rules == rules_first

    with SessionFactory() as session:
        entries = (
            session.execute(select(ConfigHistory).order_by(ConfigHistory.created_at))
            .scalars()
            .all()
        )
        assert len(entries) == 3
        assert entries[-1].note is not None
        assert "rolled_back_to" in entries[-1].note

    event_types = [event[0] for event in captured_events]
    assert event_types == [
        "config.uploaded",
        "config.uploaded",
        "config.rollback",
    ]
    rollback_event = captured_events[-1][1]
    assert rollback_event["snapshot"] == rollback_payload["rollback"]
    assert rollback_event["diff"]["layout"] is True
    assert rollback_event.get("actor") == "operator"

    post_list = client.get("/api/upload/esp-000/snapshots")
    assert post_list.status_code == 200
    post_listing = post_list.json()
    assert len(post_listing) == 2
    names = [entry["name"] for entry in post_listing]
    assert snapshots[0].name in names

    devices_response = client.get("/api/devices")
    devices_payload = devices_response.json()
    entry = next(item for item in devices_payload if item["hostname"] == "esp-000")
    assert len(entry["snapshots"]) >= 2


def test_rollback_requires_snapshot(client: TestClient) -> None:
    layout = {
        "version": "1.0",
        "widgets": [],
    }
    rules = {
        "version": "1.0",
        "actuators": [],
    }

    response = client.post(
        "/api/upload/esp-000",
        files={
            "layout": ("layout.json", json.dumps(layout), "application/json"),
            "rules": ("rules.json", json.dumps(rules), "application/json"),
        },
    )
    assert response.status_code == 200

    rollback = client.post("/api/upload/esp-000/rollback")
    assert rollback.status_code == 404



def test_stream_emits_upload_event(client: TestClient) -> None:
    layout = _load_template("layout.json")
    rules = _load_template("rules.json")
    events: queue.Queue[dict[str, object]] = queue.Queue()

    def reader() -> None:
        with client.stream("GET", "/api/stream") as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.put(json.loads(line[6:]))
                    return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    response = client.post(
        "/api/upload/esp-000",
        data={"actor": "stream"},
        files={
            "layout": ("layout.json", json.dumps(layout), "application/json"),
            "rules": ("rules.json", json.dumps(rules), "application/json"),
        },
    )
    assert response.status_code == 200
    thread.join(timeout=5)
    assert not thread.is_alive(), "SSE stream thread did not finish"
    payload = events.get_nowait()
    assert payload["hostname"] == "esp-000"
    assert payload["hashes"]["layout"] is not None
