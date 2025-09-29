"""DashMaster companion FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

from .api.devices import router as devices_router
from .api.upload import router as upload_router
from .api.stream import router as stream_router
from .store.database import init_db, SessionFactory
from .store.registry import seed_devices

app = FastAPI(title="DashMaster Companion", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with SessionFactory() as session:
        seed_devices(session)
        session.commit()


app.include_router(devices_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(stream_router, prefix="/api")


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """Basic health endpoint for readiness probes."""
    return {"status": "ok"}
