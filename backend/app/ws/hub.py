import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._job_channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._network_channel: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_job(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._job_channels[job_id].add(websocket)

    async def disconnect_job(self, job_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._job_channels[job_id].discard(websocket)
            if not self._job_channels[job_id]:
                self._job_channels.pop(job_id, None)

    async def connect_network(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._network_channel.add(websocket)

    async def disconnect_network(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._network_channel.discard(websocket)

    async def broadcast_job(self, job_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._job_channels.get(job_id, set()))
        await self._broadcast_to_sockets(sockets, payload)

    async def broadcast_network(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._network_channel)
        await self._broadcast_to_sockets(sockets, payload)

    async def _broadcast_to_sockets(self, sockets: list[WebSocket], payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        if stale:
            async with self._lock:
                for socket in stale:
                    self._network_channel.discard(socket)
                    for channel in self._job_channels.values():
                        channel.discard(socket)

