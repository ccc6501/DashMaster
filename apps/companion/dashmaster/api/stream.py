"""Server-sent events endpoint."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..core.events import bus

router = APIRouter()


@router.get("/stream")
async def stream_events() -> EventSourceResponse:
    """Subscribe to companion events."""

    async def event_generator():
        async with bus.subscribe() as queue:
            while True:
                try:
                    event = await queue.get()
                except asyncio.CancelledError:  # pragma: no cover - connection closed
                    break
                payload = event.payload | {"ts": datetime.now(UTC).isoformat()}
                yield {
                    "event": event.type,
                    "data": json.dumps(payload),
                }

    return EventSourceResponse(event_generator())
