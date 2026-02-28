from __future__ import annotations

import asyncio
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from time import perf_counter

from app.models.job import Job, JobConfig, JobCreateRequest, JobMetrics, JobStatus, NodeExecutionResult, VerificationStatus
from app.models.node import Node, NodeHeartbeatRequest, NodeRegisterRequest, NodeStatus
from app.schemas.admin import (
    AdminLiveJobItem,
    AdminLiveJobsResponse,
    NodeJobDistributionItem,
    NodeJobDistributionResponse,
)
from app.schemas.network import NetworkSnapshot, NetworkStats
from app.services.credit_ledger import CreditLedger
from app.services.scheduler import WeightedScheduler
from app.services.verifier import ResultVerifier


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryStateStore:
    def __init__(
        self,
        scheduler: WeightedScheduler | None = None,
        verifier: ResultVerifier | None = None,
        credits: CreditLedger | None = None,
        assignment_hash_secret: str = "dev-assignment-hash-secret",
        assignment_hash_ttl_sec: int = 900,
        enable_single_node_test_fallback: bool = True,
    ) -> None:
        self._node_lock = asyncio.Lock()
        self._job_lock = asyncio.Lock()
        self._nodes: dict[str, Node] = {}
        self._jobs: dict[str, Job] = {}
        self._scheduler = scheduler or WeightedScheduler()
        self._verifier = verifier or ResultVerifier()
        self._credits = credits
        self._assignment_started_at: dict[tuple[str, str], datetime] = {}
        self._assignment_hash_digests: dict[tuple[str, str], str] = {}
        self._assignment_hash_expires_at: dict[tuple[str, str], datetime] = {}
        self._assignment_hash_secret = assignment_hash_secret.encode("utf-8")
        self._assignment_hash_ttl_sec = max(60, assignment_hash_ttl_sec)
        self._job_started_at: dict[str, datetime] = {}
        self._enable_single_node_test_fallback = enable_single_node_test_fallback

    async def seed_nodes(self) -> None:
        defaults = [
            Node(id="demo-a100-1", gpu="NVIDIA A100", vram_total_gb=80, region="us-east-1"),
            Node(id="demo-h100-1", gpu="NVIDIA H100", vram_total_gb=80, region="us-west-2"),
            Node(id="demo-l40s-1", gpu="NVIDIA L40S", vram_total_gb=48, region="eu-west-1"),
            Node(id="demo-a10-1", gpu="NVIDIA A10", vram_total_gb=24, region="us-east-2"),
        ]
        async with self._node_lock:
            for node in defaults:
                self._nodes[node.id] = node

    async def register_node(self, payload: NodeRegisterRequest) -> Node:
        node_id = payload.id or f"node-{payload.gpu.lower().replace(' ', '-')}-{len(self._nodes) + 1}"
        now = utc_now()
        async with self._node_lock:
            existing = self._nodes.get(node_id)
            if existing:
                node = existing.model_copy(
                    update={
                        "gpu": payload.gpu,
                        "vram_total_gb": payload.vram_total_gb,
                        "region": payload.region,
                        "model_cache": self._normalize_model_cache(payload.model_cache),
                        # Registration creates an offline placeholder until live heartbeats begin.
                        "status": NodeStatus.offline,
                        "jobs_running": 0,
                        "last_heartbeat": now,
                    }
                )
            else:
                node = Node(
                    id=node_id,
                    gpu=payload.gpu,
                    vram_total_gb=payload.vram_total_gb,
                    region=payload.region,
                    model_cache=self._normalize_model_cache(payload.model_cache),
                    status=NodeStatus.offline,
                    jobs_running=0,
                    last_heartbeat=now,
                )
            self._nodes[node.id] = node
            return node

    async def heartbeat(self, node_id: str, payload: NodeHeartbeatRequest) -> Node:
        async with self._node_lock:
            node = self._nodes.get(node_id)
            if not node:
                raise KeyError(f"Node '{node_id}' not found")
            updates = node.model_dump()
            if payload.jobs_running is not None:
                updates["jobs_running"] = payload.jobs_running

            if payload.status == NodeStatus.offline:
                updates["status"] = NodeStatus.offline
                updates["jobs_running"] = 0
            elif payload.jobs_running is not None:
                updates["status"] = NodeStatus.busy if payload.jobs_running > 0 else NodeStatus.healthy
            elif payload.status is not None:
                updates["status"] = payload.status

            if payload.vram_used_gb is not None:
                updates["vram_used_gb"] = min(payload.vram_used_gb, node.vram_total_gb)
            if payload.latency_ms is not None:
                updates["latency_ms_avg"] = (node.latency_ms_avg * 0.7) + (payload.latency_ms * 0.3)
            if payload.model_cache is not None:
                updates["model_cache"] = self._normalize_model_cache(payload.model_cache)
            updates["last_heartbeat"] = utc_now()
            updated = Node(**updates)
            self._nodes[node_id] = updated
            return updated

    async def list_nodes(self) -> list[Node]:
        async with self._node_lock:
            return sorted(self._nodes.values(), key=lambda item: item.id)

    async def get_node(self, node_id: str) -> Node | None:
        async with self._node_lock:
            return self._nodes.get(node_id)

    async def update_node(self, node: Node) -> None:
        async with self._node_lock:
            self._nodes[node.id] = node

    async def increment_node_jobs(self, node_id: str, delta: int) -> None:
        async with self._node_lock:
            node = self._nodes.get(node_id)
            if not node:
                return
            jobs_running = max(0, node.jobs_running + delta)
            status = node.status if node.status == NodeStatus.offline else (NodeStatus.busy if jobs_running > 0 else NodeStatus.healthy)
            self._nodes[node_id] = node.model_copy(
                update={"jobs_running": jobs_running, "status": status, "last_heartbeat": utc_now()}
            )

    async def adjust_node_trust(self, node_id: str, delta: float) -> None:
        async with self._node_lock:
            node = self._nodes.get(node_id)
            if not node:
                return
            self._nodes[node_id] = node.model_copy(update={"trust_score": min(1.0, max(0.0, node.trust_score + delta))})

    async def add_model_to_node_cache(self, node_id: str, model: str) -> None:
        if not model:
            return
        async with self._node_lock:
            node = self._nodes.get(node_id)
            if not node:
                return
            cache = self._normalize_model_cache([*node.model_cache, model])
            self._nodes[node_id] = node.model_copy(update={"model_cache": cache})

    async def put_job_from_request(
        self,
        payload: JobCreateRequest,
        *,
        job_id: str | None = None,
        cost_estimate_credits: float = 0.0,
    ) -> Job:
        nodes = await self.list_nodes()
        job = Job(
            prompt=payload.prompt,
            config=payload.config,
            owner_id=payload.owner_id,
            cost_estimate_credits=round(max(0.0, cost_estimate_credits), 4),
            status=JobStatus.pending,
            progress=5,
        )
        if job_id:
            job = job.model_copy(update={"id": job_id})
        target = self._target_replicas(job, nodes)
        plan = self._plan_nodes_for_job(nodes, job.config, target)
        job = job.model_copy(update={"scheduled_node_ids": [node.id for node in plan]})
        await self.put_job(job)
        return job

    async def put_job(self, job: Job) -> None:
        async with self._job_lock:
            self._jobs[job.id] = job

    async def get_job(self, job_id: str) -> Job | None:
        async with self._job_lock:
            return self._jobs.get(job_id)

    async def list_jobs(self) -> list[Job]:
        async with self._job_lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    async def touch_job(self, job_id: str, **updates: object) -> Job:
        async with self._job_lock:
            existing = self._jobs.get(job_id)
            if not existing:
                raise KeyError(f"Job '{job_id}' not found")
            payload = existing.model_dump()
            payload.update(updates)
            payload["updated_at"] = utc_now()
            updated = Job(**payload)
            self._jobs[job_id] = updated
            return updated

    async def append_job_log(self, job_id: str, message: str, level: str = "info", node_id: str | None = None) -> Job:
        job = await self.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")
        return await self.touch_job(job_id, logs=[*job.logs, {"message": message, "level": level, "node_id": node_id}])

    async def claim_next_job(self, node_id: str) -> tuple[Job, str, datetime] | None:
        node = await self.get_node(node_id)
        if not node:
            raise KeyError(f"Node '{node_id}' not found")
        if node.status == NodeStatus.offline:
            return None

        now = utc_now()
        nodes = await self.list_nodes()
        claimed: Job | None = None
        assignment_hash_key: str | None = None
        assignment_expires_at: datetime | None = None
        async with self._job_lock:
            for job in sorted(self._jobs.values(), key=lambda item: item.created_at):
                if job.status in {JobStatus.completed, JobStatus.failed, JobStatus.verifying}:
                    continue
                target = self._target_replicas(job, nodes)
                successful = self._successful(job)
                inflight = set(job.inflight_node_ids)
                needed = target - (len(successful) + len(inflight))
                if needed <= 0 or node_id in inflight:
                    continue
                if any(result.node_id == node_id and result.success for result in successful):
                    continue
                strict_ranked = self._scheduler.rank_nodes(nodes, job.config, exclude_node_ids=inflight)
                ranked = strict_ranked or self._rank_nodes_for_job(nodes, job.config, exclude_node_ids=inflight)
                if not ranked:
                    continue
                if node_id not in {item.id for item in ranked[: min(len(ranked), max(target, needed * 2))]}:
                    continue
                if job.id not in self._job_started_at:
                    self._job_started_at[job.id] = now
                queue_ms = (self._job_started_at[job.id] - job.created_at).total_seconds() * 1000
                execution_ms = (now - self._job_started_at[job.id]).total_seconds() * 1000
                inflight_ids = [*dict.fromkeys([*job.inflight_node_ids, node_id])]
                progress = self._progress(len(successful), len(inflight_ids), target)
                fallback_logs = []
                if not strict_ranked and self._single_node_fallback_nodes(nodes):
                    fallback_logs.append(
                        {
                            "message": "Single-node fallback assignment active (capacity filter relaxed for MVP testing).",
                            "level": "warning",
                            "node_id": node_id,
                        }
                    )
                claimed = job.model_copy(
                    update={
                        "status": JobStatus.running,
                        "verification_status": VerificationStatus.pending,
                        "inflight_node_ids": inflight_ids,
                        "assigned_node_ids": [*dict.fromkeys([*job.assigned_node_ids, node_id])],
                        "scheduled_node_ids": [item.id for item in ranked[:target]],
                        "progress": progress,
                        "metrics": JobMetrics(
                            queue_ms=round(queue_ms, 2),
                            execution_ms=round(execution_ms, 2),
                            verification_ms=job.metrics.verification_ms,
                            total_ms=round(queue_ms + execution_ms + job.metrics.verification_ms, 2),
                        ),
                        "logs": [
                            *job.logs,
                            {"message": f"Replica claimed by {node_id}", "level": "info", "node_id": node_id},
                            *fallback_logs,
                        ],
                        "updated_at": now,
                    }
                )
                self._jobs[job.id] = claimed
                self._assignment_started_at[(job.id, node_id)] = now
                assignment_hash_key, assignment_expires_at = self._issue_assignment_hash_key(job.id, node_id, now)
                break

        if not claimed:
            return None
        if not assignment_hash_key or not assignment_expires_at:
            raise RuntimeError(f"failed_to_issue_assignment_hash_key for {claimed.id}:{node_id}")
        await self.increment_node_jobs(node_id, 1)
        await self.add_model_to_node_cache(node_id, claimed.config.model)
        return claimed, assignment_hash_key, assignment_expires_at

    async def submit_job_result(
        self,
        node_id: str,
        job_id: str,
        output: str,
        latency_ms: float | None = None,
        assignment_hash_key: str | None = None,
    ) -> Job:
        return await self._submit_replica(
            node_id,
            job_id,
            output=output,
            latency_ms=latency_ms,
            error=None,
            assignment_hash_key=assignment_hash_key,
        )

    async def submit_job_failure(
        self,
        node_id: str,
        job_id: str,
        error: str,
        assignment_hash_key: str | None = None,
    ) -> Job:
        return await self._submit_replica(
            node_id,
            job_id,
            output=None,
            latency_ms=None,
            error=error,
            assignment_hash_key=assignment_hash_key,
        )

    async def _submit_replica(
        self,
        node_id: str,
        job_id: str,
        output: str | None,
        latency_ms: float | None,
        error: str | None,
        assignment_hash_key: str | None,
    ) -> Job:
        now = utc_now()
        key = (job_id, node_id)
        async with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found")
            if job.status == JobStatus.completed:
                return job
            if job.status == JobStatus.failed:
                raise ValueError(f"Job '{job_id}' already failed")
            if node_id not in job.inflight_node_ids and key not in self._assignment_started_at:
                raise ValueError(f"Node '{node_id}' has no active assignment for job '{job_id}'")
            self._verify_assignment_hash_key(
                job_id=job_id,
                node_id=node_id,
                assignment_hash_key=assignment_hash_key,
                now=now,
            )

            self._assignment_started_at.pop(key, None)
            self._clear_assignment_hash_key(job_id, node_id)
            inflight = [item for item in job.inflight_node_ids if item != node_id]
            started_at = self._job_started_at.get(job_id, job.updated_at)
            execution_ms = max(0.0, (now - started_at).total_seconds() * 1000)
            result = NodeExecutionResult(
                node_id=node_id,
                output=output,
                latency_ms=float(latency_ms if latency_ms is not None else execution_ms),
                success=error is None,
                error=error,
            )
            results = [item for item in job.results if item.node_id != node_id]
            results.append(result)
            failed_nodes = job.failed_node_ids if error is None else [*dict.fromkeys([*job.failed_node_ids, node_id])]
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": JobStatus.running,
                    "results": results,
                    "inflight_node_ids": inflight,
                    "failed_node_ids": failed_nodes,
                    "logs": [
                        *job.logs,
                        {
                            "message": f"Replica {'failed' if error else 'result'} from {node_id}",
                            "level": "error" if error else "info",
                            "node_id": node_id,
                        },
                    ],
                    "updated_at": now,
                }
            )

        await self.increment_node_jobs(node_id, -1)
        await self.adjust_node_trust(node_id, -0.03 if error else 0.0)
        try:
            await self.heartbeat(node_id, NodeHeartbeatRequest(latency_ms=latency_ms, jobs_running=0))
        except KeyError:
            pass
        final = await self._evaluate_job(job_id)
        if self._credits and final.status == JobStatus.failed and final.cost_estimate_credits > 0:
            await self._credits.refund_user(final.owner_id, final.id, final.cost_estimate_credits)
        return final

    async def _evaluate_job(self, job_id: str) -> Job:
        nodes = await self.list_nodes()
        verify_data: tuple[list[NodeExecutionResult], int] | None = None
        async with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found")
            if job.status in {JobStatus.completed, JobStatus.failed}:
                return job
            successful = self._successful(job)
            target = self._target_replicas(job, nodes)
            inflight = set(job.inflight_node_ids)
            used = {item.node_id for item in successful} | inflight
            remaining = self._rank_nodes_for_job(nodes, job.config, exclude_node_ids=used)
            if len(successful) >= target or (len(successful) > 0 and not inflight and not remaining):
                self._jobs[job_id] = job.model_copy(update={"status": JobStatus.verifying, "progress": 92})
                verify_data = (successful, target)
            elif len(successful) == 0 and not inflight and not remaining:
                failed = job.model_copy(
                    update={
                        "status": JobStatus.failed,
                        "verification_status": VerificationStatus.failed,
                        "progress": 100,
                        "error": "No healthy nodes available to execute replicas",
                    }
                )
                self._jobs[job_id] = failed
                return failed
            else:
                self._jobs[job_id] = job.model_copy(
                    update={
                        "status": JobStatus.running if inflight else JobStatus.pending,
                        "progress": self._progress(len(successful), len(inflight), target),
                        "scheduled_node_ids": [item.id for item in self._plan_nodes_for_job(nodes, job.config, target)],
                    }
                )
                return self._jobs[job_id]

        if not verify_data:
            job = await self.get_job(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found")
            return job

        successful, target = verify_data
        started = perf_counter()
        v_status, merged, confidence, details = self._verifier.verify(successful, expected_replicas=target)
        verification_ms = (perf_counter() - started) * 1000

        async with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found")
            job_started = self._job_started_at.get(job_id, job.created_at)
            queue_ms = float(job.metrics.queue_ms)
            execution_ms = max(0.0, (utc_now() - job_started).total_seconds() * 1000)
            final_status = JobStatus.completed if v_status != VerificationStatus.failed else JobStatus.failed
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": final_status,
                    "verification_status": v_status,
                    "merged_output": merged,
                    "verification_confidence": confidence,
                    "verification_details": details,
                    "inflight_node_ids": [],
                    "progress": 100,
                    "error": None if final_status == JobStatus.completed else "Verification failed",
                    "metrics": JobMetrics(
                        queue_ms=round(queue_ms, 2),
                        execution_ms=round(execution_ms, 2),
                        verification_ms=round(verification_ms, 2),
                        total_ms=round(queue_ms + execution_ms + verification_ms, 2),
                    ),
                    "logs": [
                        *job.logs,
                        {"message": f"Verification {v_status.value}", "level": "info", "node_id": None},
                    ],
                    "updated_at": utc_now(),
                }
            )
            stale = [key for key in self._assignment_started_at if key[0] == job_id]
            for key in stale:
                self._assignment_started_at.pop(key, None)
                self._clear_assignment_hash_key(*key)
        await self._apply_trust(await self.get_job(job_id))
        final = await self.get_job(job_id)
        if not final:
            raise KeyError(f"Job '{job_id}' not found")
        return final

    async def _apply_trust(self, job: Job | None) -> None:
        if not job:
            return
        majority = set(job.verification_details.get("majority_nodes", []))
        for result in job.results:
            if not result.success:
                await self.adjust_node_trust(result.node_id, -0.01)
            elif result.node_id in majority:
                await self.adjust_node_trust(result.node_id, 0.015)
                await self._reward_node_for_job(job, result.node_id, 1.15)
            else:
                await self.adjust_node_trust(result.node_id, -0.01)
                await self._reward_node_for_job(job, result.node_id, 0.55)

    async def _reward_node_for_job(self, job: Job, node_id: str, multiplier: float) -> None:
        if not self._credits:
            return
        base = max(0.1, (job.cost_estimate_credits / max(1, job.config.replicas)))
        reward = round(base * max(0.2, multiplier), 4)
        await self._credits.reward_node(node_id=node_id, job_id=job.id, amount=reward, reason="job_execution")

    async def expire_stale_job_claims(self, timeout_seconds: int) -> set[str]:
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        affected: set[str] = set()
        nodes: set[str] = set()
        async with self._job_lock:
            stale = [(job_id, node_id) for (job_id, node_id), ts in self._assignment_started_at.items() if ts < cutoff]
            for job_id, node_id in stale:
                self._assignment_started_at.pop((job_id, node_id), None)
                self._clear_assignment_hash_key(job_id, node_id)
                job = self._jobs.get(job_id)
                if not job or node_id not in job.inflight_node_ids:
                    continue
                self._jobs[job_id] = job.model_copy(
                    update={
                        "status": JobStatus.running if len(job.inflight_node_ids) > 1 else JobStatus.pending,
                        "inflight_node_ids": [item for item in job.inflight_node_ids if item != node_id],
                        "failed_node_ids": [*dict.fromkeys([*job.failed_node_ids, node_id])],
                        "logs": [*job.logs, {"message": f"Replica lease expired for {node_id}", "level": "warning", "node_id": node_id}],
                    }
                )
                affected.add(job_id)
                nodes.add(node_id)
        for node_id in nodes:
            await self.increment_node_jobs(node_id, -1)
            await self.adjust_node_trust(node_id, -0.01)
        for job_id in list(affected):
            await self._evaluate_job(job_id)
        return affected

    async def expire_stale_nodes(self, timeout_seconds: int) -> set[str]:
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        offline: set[str] = set()
        async with self._node_lock:
            for node_id, node in list(self._nodes.items()):
                if node.last_heartbeat < cutoff and node.status != NodeStatus.offline:
                    self._nodes[node_id] = node.model_copy(update={"status": NodeStatus.offline, "jobs_running": 0})
                    offline.add(node_id)
        if not offline:
            return set()
        return await self._release_inflight(offline, "Assigned node went offline. Replica will be reassigned.")

    async def _release_inflight(self, node_ids: set[str], message: str) -> set[str]:
        affected: set[str] = set()
        async with self._job_lock:
            stale = [key for key in self._assignment_started_at if key[1] in node_ids]
            for key in stale:
                self._assignment_started_at.pop(key, None)
                self._clear_assignment_hash_key(*key)
            for job_id, job in list(self._jobs.items()):
                if not any(item in node_ids for item in job.inflight_node_ids):
                    continue
                self._jobs[job_id] = job.model_copy(
                    update={
                        "status": JobStatus.running if len(job.inflight_node_ids) > 1 else JobStatus.pending,
                        "inflight_node_ids": [item for item in job.inflight_node_ids if item not in node_ids],
                        "failed_node_ids": [*dict.fromkeys([*job.failed_node_ids, *[item for item in job.inflight_node_ids if item in node_ids]])],
                        "logs": [*job.logs, {"message": message, "level": "warning", "node_id": None}],
                    }
                )
                affected.add(job_id)
        for node_id in node_ids:
            await self.adjust_node_trust(node_id, -0.02)
        for job_id in list(affected):
            await self._evaluate_job(job_id)
        return affected

    async def synthetic_pulse(self) -> None:
        async with self._node_lock:
            for node_id, node in list(self._nodes.items()):
                if not node_id.startswith("demo-"):
                    continue
                if node.status == NodeStatus.offline and node.jobs_running == 0:
                    continue
                self._nodes[node_id] = node.model_copy(
                    update={"status": NodeStatus.busy if node.jobs_running > 0 else NodeStatus.healthy, "last_heartbeat": utc_now()}
                )

    async def network_stats(self) -> NetworkStats:
        nodes = await self.list_nodes()
        jobs = await self.list_jobs()
        latencies = [item.latency_ms_avg for item in nodes if item.latency_ms_avg > 0]
        return NetworkStats(
            active_nodes=len([item for item in nodes if item.status != NodeStatus.offline]),
            total_nodes=len(nodes),
            total_vram_gb=round(sum(item.vram_total_gb for item in nodes), 2),
            jobs_running=len([job for job in jobs if job.status in {JobStatus.pending, JobStatus.running, JobStatus.verifying}]),
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        )

    async def network_snapshot(self) -> NetworkSnapshot:
        stats = await self.network_stats()
        return NetworkSnapshot(stats=stats, nodes=await self.list_nodes(), running_jobs=stats.jobs_running)

    async def jobs_status_counts(self) -> dict[JobStatus, int]:
        counter: Counter[JobStatus] = Counter(job.status for job in await self.list_jobs())
        return {status: counter.get(status, 0) for status in JobStatus}

    async def jobs_distribution(self) -> NodeJobDistributionResponse:
        return NodeJobDistributionResponse(
            items=[
                NodeJobDistributionItem(
                    node_id=node.id,
                    jobs=node.jobs_running,
                    status=node.status,
                    trust_score=node.trust_score,
                )
                for node in await self.list_nodes()
            ]
        )

    async def admin_live_jobs(self, limit: int = 50) -> AdminLiveJobsResponse:
        items: list[AdminLiveJobItem] = []
        for job in (await self.list_jobs())[:limit]:
            items.append(
                AdminLiveJobItem(
                    job_id=job.id,
                    status=job.status,
                    verification_status=job.verification_status,
                    prompt_preview=job.prompt[:120],
                    model=job.config.model,
                    target_replicas=max(1, job.config.replicas),
                    successful_replicas=len(self._successful(job)),
                    inflight_replicas=len(job.inflight_node_ids),
                    assigned_node_ids=job.assigned_node_ids,
                    failed_node_ids=job.failed_node_ids,
                    verification_confidence=job.verification_confidence,
                    updated_at=job.updated_at,
                )
            )
        return AdminLiveJobsResponse(items=items)

    def _target_replicas(self, job: Job, nodes: list[Node]) -> int:
        eligible = [node for node in nodes if self._scheduler.rank_nodes([node], job.config)]
        if eligible:
            return max(1, min(job.config.replicas, len(eligible)))
        active_nodes = [node for node in nodes if node.status != NodeStatus.offline]
        if self._should_use_single_node_fallback(active_nodes):
            return 1
        return max(1, min(job.config.replicas, len(active_nodes) if active_nodes else 1))

    def _plan_nodes_for_job(self, nodes: list[Node], config: JobConfig, replicas: int) -> list[Node]:
        plan = self._scheduler.select_nodes(nodes, config, replicas)
        if plan:
            return plan
        return self._single_node_fallback_nodes(nodes)[:replicas]

    def _rank_nodes_for_job(
        self,
        nodes: list[Node],
        config: JobConfig,
        exclude_node_ids: set[str] | None = None,
    ) -> list[Node]:
        ranked = self._scheduler.rank_nodes(nodes, config, exclude_node_ids=exclude_node_ids)
        if ranked:
            return ranked

        fallback = self._single_node_fallback_nodes(nodes)
        if not fallback:
            return []

        exclude = exclude_node_ids or set()
        return [node for node in fallback if node.id not in exclude]

    def _single_node_fallback_nodes(self, nodes: list[Node]) -> list[Node]:
        active_nodes = [node for node in nodes if node.status != NodeStatus.offline]
        if not self._should_use_single_node_fallback(active_nodes):
            return []
        return sorted(
            active_nodes,
            key=lambda node: (
                1 if node.status == NodeStatus.healthy else 0,
                node.trust_score,
                node.free_vram_gb,
                node.id,
            ),
            reverse=True,
        )

    def _should_use_single_node_fallback(self, active_nodes: list[Node]) -> bool:
        return self._enable_single_node_test_fallback and len(active_nodes) == 1

    def _successful(self, job: Job) -> list[NodeExecutionResult]:
        return [item for item in job.results if item.success and item.output]

    def _progress(self, successful: int, inflight: int, target: int) -> float:
        if target <= 0:
            return 15
        ratio = min(1.0, (successful + inflight * 0.45) / target)
        return round(min(88, max(12, 12 + ratio * 72)), 2)

    def _normalize_model_cache(self, models: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for model in models:
            cleaned = str(model).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(cleaned)
        return unique[:32]

    def _issue_assignment_hash_key(self, job_id: str, node_id: str, now: datetime) -> tuple[str, datetime]:
        expires_at = now + timedelta(seconds=self._assignment_hash_ttl_sec)
        expires_at = expires_at.replace(microsecond=0)
        exp_ts = int(expires_at.timestamp())
        nonce = secrets.token_urlsafe(16)
        payload = f"{job_id}:{node_id}:{exp_ts}:{nonce}"
        digest = hmac.new(self._assignment_hash_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        signature = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        assignment_hash_key = f"{nonce}.{exp_ts}.{signature}"
        assignment_key = (job_id, node_id)
        self._assignment_hash_digests[assignment_key] = hashlib.sha256(assignment_hash_key.encode("utf-8")).hexdigest()
        self._assignment_hash_expires_at[assignment_key] = expires_at
        return assignment_hash_key, expires_at

    def _verify_assignment_hash_key(
        self,
        *,
        job_id: str,
        node_id: str,
        assignment_hash_key: str | None,
        now: datetime,
    ) -> None:
        assignment_key = (job_id, node_id)
        expected_digest = self._assignment_hash_digests.get(assignment_key)
        expected_expires_at = self._assignment_hash_expires_at.get(assignment_key)
        if not expected_digest or not expected_expires_at:
            raise ValueError(f"Missing active assignment hash key for node '{node_id}'")
        if not assignment_hash_key:
            raise ValueError("Missing assignment hash key")

        parts = assignment_hash_key.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed assignment hash key")
        nonce, exp_raw, provided_signature = parts
        if not nonce or not exp_raw or not provided_signature:
            raise ValueError("Malformed assignment hash key")
        try:
            exp_ts = int(exp_raw)
        except ValueError as exc:
            raise ValueError("Malformed assignment hash key") from exc

        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        if expires_at != expected_expires_at:
            raise ValueError("Assignment hash key is not valid for this claim")
        if expires_at < now:
            raise ValueError("Assignment hash key expired")

        payload = f"{job_id}:{node_id}:{exp_ts}:{nonce}"
        expected_sig_raw = hmac.new(self._assignment_hash_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        expected_signature = base64.urlsafe_b64encode(expected_sig_raw).decode("utf-8").rstrip("=")
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("Invalid assignment hash key signature")

        provided_digest = hashlib.sha256(assignment_hash_key.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(provided_digest, expected_digest):
            raise ValueError("Assignment hash key does not match active claim")

    def _clear_assignment_hash_key(self, job_id: str, node_id: str) -> None:
        assignment_key = (job_id, node_id)
        self._assignment_hash_digests.pop(assignment_key, None)
        self._assignment_hash_expires_at.pop(assignment_key, None)
