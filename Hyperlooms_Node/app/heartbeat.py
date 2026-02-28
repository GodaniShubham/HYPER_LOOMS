from __future__ import annotations

import asyncio
from datetime import datetime

from app.gpu_detector import get_vram_used_gb
from app.state import AgentState
from app.coordinator_client import CoordinatorClient


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: int) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


async def heartbeat_loop(
    state: AgentState,
    client: CoordinatorClient,
    endpoint: str,
    interval_sec: int,
    stop_event: asyncio.Event,
    logger,
) -> None:
    while not stop_event.is_set():
        if not state.node_id:
            await _sleep_or_stop(stop_event, interval_sec)
            continue
        if not state.connected:
            state.last_event = "heartbeat_paused_coordinator_down"
            state.touch()
            await _sleep_or_stop(stop_event, interval_sec)
            continue

        jobs_running = 0 if state.current_job_status in {"idle", ""} else 1
        payload = {
            "status": "busy" if jobs_running > 0 else "healthy",
            "vram_used_gb": get_vram_used_gb(logger),
            "latency_ms": None,
            "jobs_running": jobs_running,
            "model_cache": state.model_cache,
        }
        try:
            response = await client.heartbeat(endpoint, payload)
            if response is None:
                state.registered = False
                state.registration_status = "not-registered"
                state.last_error = "heartbeat_failed: node_not_registered_remote"
                state.last_event = "heartbeat_node_not_registered"
                state.touch()
                await _sleep_or_stop(stop_event, interval_sec)
                continue
            state.last_heartbeat = datetime.now()
            state.last_event = "heartbeat"
        except Exception as exc:  # noqa: BLE001
            state.connected = False
            state.last_error = f"heartbeat_failed: {exc}"
            logger.warning("heartbeat_failed", extra={"error": str(exc)})
        state.touch()
        await _sleep_or_stop(stop_event, interval_sec)
