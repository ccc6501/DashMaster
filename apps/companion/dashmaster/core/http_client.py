"""Minimal HTTP client for device communication."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Mapping

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


def _device_base_url(hostname: str, http_port: int) -> str:
    template = os.getenv("DEVICE_HTTP_BASE", "http://127.0.0.1:{port}")
    return template.format(hostname=hostname, port=http_port)


class DeviceClient:
    """Helper for interacting with device REST endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=5.0,
            transport=transport,
        )

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def post_json(self, path: str, payload: Any) -> httpx.Response:
        return await self._client.post(path, json=payload)

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def post_bytes(self, path: str, payload: bytes, content_type: str) -> httpx.Response:
        return await self._client.post(
            path,
            content=payload,
            headers={"Content-Type": content_type},
        )

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def post(self, path: str, *, params: Mapping[str, Any] | None = None) -> httpx.Response:
        return await self._client.post(path, params=params)

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def get(self, path: str) -> httpx.Response:
        return await self._client.get(path)

    async def close(self) -> None:
        await self._client.aclose()


@asynccontextmanager
async def create_device_client(
    *,
    hostname: str,
    http_port: int,
    transport: httpx.BaseTransport | None = None,
) -> AsyncIterator[DeviceClient]:
    client = DeviceClient(
        _device_base_url(hostname, http_port),
        transport=transport,
    )
    try:
        yield client
    finally:
        await client.close()
