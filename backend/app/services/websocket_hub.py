import asyncio
from collections import defaultdict

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._job_channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._network_channels: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect_job(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._job_channels[job_id].add(websocket)

    async def disconnect_job(self, job_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._job_channels.get(job_id)
            if not clients:
                return
            clients.discard(websocket)
            if not clients:
                self._job_channels.pop(job_id, None)

    async def connect_network(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._network_channels.add(websocket)

    async def disconnect_network(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._network_channels.discard(websocket)

    async def broadcast_job(self, job_id: str, payload: dict) -> None:
        clients = list(self._job_channels.get(job_id, []))
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(client)
        for client in stale:
            await self.disconnect_job(job_id, client)

    async def broadcast_network(self, payload: dict) -> None:
        clients = list(self._network_channels)
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(client)
        for client in stale:
            await self.disconnect_network(client)

