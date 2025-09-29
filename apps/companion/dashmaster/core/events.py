"""In-memory event bus for SSE streaming."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Event:
    """Simple event envelope."""

    type: str
    payload: dict[str, Any]


class EventBus:
    """Lightweight pub/sub fan-out implemented with asyncio queues."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = Event(event_type, payload)
        async with self._lock:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop events for slow subscribers to avoid back-pressure.
                    continue

    @asynccontextmanager
    async def subscribe(self, max_queue_size: int = 100) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(max_queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)


bus = EventBus()
