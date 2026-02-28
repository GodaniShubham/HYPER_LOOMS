from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.logging import get_logger
from app.models.job import Job, JobCreateRequest, JobStatus
from app.services.credit_ledger import CreditLedger
from app.services.state_store import InMemoryStateStore
from app.ws.hub import WebSocketHub


class JobOrchestrator:
    """
    Coordinator-side job queue manager.

    Real execution is performed by external node agents via:
    - GET /api/v1/nodes/{node_id}/jobs/next
    - POST /api/v1/nodes/{node_id}/jobs/{job_id}/result
    - POST /api/v1/nodes/{node_id}/jobs/{job_id}/fail
    """

    def __init__(
        self,
        state: InMemoryStateStore,
        scheduler,  # kept for backwards-compatible wiring
        verifier,  # kept for backwards-compatible wiring
        hub: WebSocketHub,
        credits: CreditLedger | None = None,
    ) -> None:
        self.state = state
        self.scheduler = scheduler
        self.verifier = verifier
        self.hub = hub
        self.credits = credits
        self.logger = get_logger("computefabric.orchestrator")

    async def submit_job(self, payload: JobCreateRequest) -> Job:
        job_id = f"job-{uuid4().hex[:12]}"
        estimated_credits = 0.0
        if self.credits:
            estimated_credits = await self.credits.estimate_job_cost(payload.config)
            await self.credits.charge_user_for_job(payload.owner_id, job_id, estimated_credits)

        job = await self.state.put_job_from_request(
            payload,
            job_id=job_id,
            cost_estimate_credits=estimated_credits,
        )

        if job.scheduled_node_ids:
            await self.state.append_job_log(
                job.id,
                f"Job accepted and queued. Planned nodes: {', '.join(job.scheduled_node_ids)}",
                level="info",
            )
        else:
            await self.state.append_job_log(job.id, "Job accepted and queued", level="info")
        await self.state.touch_job(job.id, status=JobStatus.pending, progress=5)
        await self._emit_job_update(job.id)
        await self._emit_network_update()
        self.logger.info(
            "job_queued",
            extra={
                "job_id": job.id,
                "owner_id": payload.owner_id,
                "estimated_credits": estimated_credits,
                "event": "job.queued",
            },
        )
        return (await self.state.get_job(job.id)) or job

    async def retry_job(self, job_id: str) -> Job:
        existing = await self.state.get_job(job_id)
        if not existing:
            raise KeyError(f"Job '{job_id}' not found")
        payload = JobCreateRequest(prompt=existing.prompt, config=existing.config, owner_id=existing.owner_id)
        retry = await self.submit_job(payload)
        await self.state.append_job_log(retry.id, f"Created as retry from {job_id}", level="info")
        await self._emit_job_update(retry.id)
        return retry

    async def _emit_job_update(self, job_id: str) -> None:
        job = await self.state.get_job(job_id)
        if not job:
            return
        await self.hub.broadcast_job(job_id, {"event": "job_update", "job": job.model_dump(mode="json")})

    async def _emit_network_update(self) -> None:
        snapshot = await self.state.network_snapshot()
        await self.hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})

    async def emit_job_log(
        self,
        job_id: str,
        message: str,
        level: str = "info",
        node_id: str | None = None,
        event: str = "job.log",
    ) -> None:
        job = await self.state.append_job_log(job_id, message=message, level=level, node_id=node_id)
        payload: dict[str, Any] = {
            "event": "log",
            "job_id": job_id,
            "entry": job.logs[-1].model_dump(mode="json"),
        }
        await self.hub.broadcast_job(job_id, payload)
        self.logger.log(
            level=40 if level == "error" else 20,
            msg=message,
            extra={"job_id": job_id, "node_id": node_id, "event": event},
        )
