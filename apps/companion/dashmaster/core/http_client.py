"""Minimal HTTP client for device communication."""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class DeviceClient:
    """Helper for interacting with device REST endpoints."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def post_json(self, path: str, payload: Any) -> httpx.Response:
        return await self._client.post(path, json=payload)

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def get(self, path: str) -> httpx.Response:
        return await self._client.get(path)

    async def close(self) -> None:
        await self._client.aclose()
