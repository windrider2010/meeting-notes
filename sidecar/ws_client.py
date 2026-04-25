from __future__ import annotations

import asyncio
from typing import Any

import orjson
import websockets


class WSClient:
    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self.ws: Any | None = None
        self._send_lock = asyncio.Lock()

    async def connect(self) -> Any:
        self.ws = await websockets.connect(
            self.ws_url,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        return self.ws

    async def send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._send_json_unlocked(payload)

    async def send_audio_chunk(self, meta: dict[str, Any], pcm: bytes) -> None:
        async with self._send_lock:
            await self._send_json_unlocked(meta)
            await self._send_bytes_unlocked(pcm)

    async def recv(self) -> str | bytes:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        return await self.ws.recv()

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()

    async def _send_json_unlocked(self, payload: dict[str, Any]) -> None:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send(orjson.dumps(payload).decode("utf-8"))

    async def _send_bytes_unlocked(self, payload: bytes) -> None:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send(payload)
