"""Minimal device emulator for backend tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="DashMaster Device Emulator")

_STORAGE = Path(__file__).resolve().parent / "_emu_storage"
_STORAGE.mkdir(exist_ok=True)

_STATUS = {
    "id": "emu-001",
    "hostname": "esp-emu.local",
    "profile": "sandbox",
    "version": "0.1.0",
    "uptime": 123,
    "rssi": -50,
    "capabilities": ["sse", "http"],
}

_SCHEMA = {"version": "1.0", "sensors": []}
_STATE = {"temp": 23.4}


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return _STATUS


@app.get("/api/schema")
async def schema() -> dict[str, Any]:
    return _SCHEMA


@app.get("/api/state")
async def state() -> dict[str, Any]:
    return _STATE


@app.post("/api/layout")
async def layout(request: Request) -> Response:
    content = await request.body()
    (_STORAGE / "layout.json").write_bytes(content)
    return Response(status_code=200)


@app.post("/api/rules")
async def rules(request: Request) -> Response:
    content = await request.body()
    (_STORAGE / "rules.json").write_bytes(content)
    return Response(status_code=200)


@app.get("/api/stream")
async def stream() -> EventSourceResponse:
    async def generator():
        yield {"event": "telemetry", "data": {"temp": 23.4}}

    return EventSourceResponse(generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=18080)
