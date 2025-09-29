"""Simple TCP port mapper for DashMaster development.

The mapper exposes localhost:8100-8124 and 8200-8224, forwarding traffic to
esp-000.local … esp-024.local on port 80. Admin routes strip the `/admin`
prefix, matching the behaviour of the production ingress.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(slots=True)
class PortMapping:
    local_port: int
    target_host: str
    target_port: int = 80
    strip_prefix: str | None = None


def build_mappings() -> list[PortMapping]:
    mappings: list[PortMapping] = []
    for idx in range(25):
        hostname = f"esp-{idx:03}.local"
        mappings.append(PortMapping(local_port=8100 + idx, target_host=hostname))
        mappings.append(
            PortMapping(
                local_port=8200 + idx,
                target_host=hostname,
                strip_prefix="/admin",
            )
        )
    return mappings


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, mapping: PortMapping) -> None:
    try:
        remote_reader, remote_writer = await asyncio.open_connection(
            mapping.target_host, mapping.target_port
        )
    except OSError as exc:
        writer.close()
        await writer.wait_closed()
        raise RuntimeError(
            f"Failed to connect to {mapping.target_host}:{mapping.target_port}: {exc}"
        ) from exc

    try:
        header = await reader.readuntil(b"\r\n\r\n")
    except asyncio.IncompleteReadError as exc:
        remote_writer.close()
        await remote_writer.wait_closed()
        writer.close()
        await writer.wait_closed()
        raise RuntimeError("Client disconnected before sending headers") from exc

    if mapping.strip_prefix:
        header = rewrite_request_path(header, mapping.strip_prefix)

    remote_writer.write(header)
    await remote_writer.drain()

    async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                chunk = await src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        finally:
            dst.close()
            with contextlib.suppress(Exception):
                await dst.wait_closed()

    import contextlib

    await asyncio.gather(
        pump(reader, remote_writer),
        pump(remote_reader, writer),
    )


def rewrite_request_path(header: bytes, prefix: str) -> bytes:
    request_line, remainder = header.split(b"\r\n", 1)
    parts = request_line.split(b" ")
    if len(parts) != 3:
        return header
    method, path, version = parts
    if path.startswith(prefix.encode("utf-8")):
        new_path = path[len(prefix) :] or b"/"
        request_line = b" ".join([method, new_path, version])
    return request_line + b"\r\n" + remainder


async def start_server(mapping: PortMapping) -> asyncio.base_events.Server:
    return await asyncio.start_server(
        lambda r, w: handle_connection(r, w, mapping),
        host="127.0.0.1",
        port=mapping.local_port,
    )


async def main() -> None:
    mappings = build_mappings()
    servers = [await start_server(mapping) for mapping in mappings]
    for mapping in mappings:
        print(
            f"Forwarding 127.0.0.1:{mapping.local_port} -> {mapping.target_host}:{mapping.target_port}"
        )
    try:
        await asyncio.gather(*(server.serve_forever() for server in servers))
    except asyncio.CancelledError:  # pragma: no cover - shutdown
        pass
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
