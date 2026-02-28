from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import threading
from typing import Any, Coroutine
from uuid import uuid4

from app.container_runner import ContainerExecutionConfig, DockerSandboxRunner
from app.config import AgentConfig, get_trust_path, save_config
from app.coordinator_client import CoordinatorClient
from app.device_probe import collect_device_snapshot, format_debug_trace, format_snapshot
from app.gpu_detector import detect_gpu, get_system_ram_gb, get_vram_used_gb
from app.heartbeat import heartbeat_loop
from app.job_worker import job_worker_loop
from app.state import AgentState
from app.trust_manager import TrustManager

DEFAULT_FABRIC_MODEL = "fabric-workload-v1"


class AgentController:
    STATUS_POLL_SEC = 4
    AUTO_REGISTER_BACKOFF_SEC = 10
    TASK_SNAPSHOT_SEC = 5

    def __init__(self, config: AgentConfig, state: AgentState, event_queue, logger) -> None:
        self._config = config
        self._state = state
        self._queue = event_queue
        self._logger = logger

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

        self._client: CoordinatorClient | None = None
        self._trust: TrustManager | None = None
        self._sandbox_runner: DockerSandboxRunner | None = None

        self._status_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._job_task: asyncio.Task | None = None

        self._services_running = False
        self._runtime_enabled = False
        self._last_auto_register_attempt: datetime | None = None
        self._last_task_snapshot_at: datetime | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_services(self) -> None:
        if self._services_running:
            self.emit("console", {"message": "services_already_running"})
            return

        self._services_running = True
        self._state.node_agent_status = "starting"
        self._state.services_started_at = datetime.now()
        self._state.touch()

        if not self.is_running():
            self._thread = threading.Thread(target=self._run_thread, daemon=True)
            self._thread.start()

        # Promote registered nodes from offline->healthy as soon as services come online.
        if self._state.registered and self._state.node_id:
            self._submit_async(self._send_presence_heartbeat(status="healthy", jobs_running=0, event_name="services_online"))

        self.emit("console", {"message": "services_started"})
        self._emit_status()

    def stop_services(self) -> None:
        if not self._services_running:
            self.emit("console", {"message": "services_already_stopped"})
            return

        if self._state.registered and self._state.node_id:
            # Push offline immediately so web UI reflects service stop without waiting for timeout.
            self._submit_async(self._send_presence_heartbeat(status="offline", jobs_running=0, event_name="services_offline"))

        self._services_running = False
        self._runtime_enabled = False

        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

        thread_alive = False
        if self._thread:
            self._thread.join(timeout=1.5)
            thread_alive = self._thread.is_alive()
        if not thread_alive:
            self._thread = None
            self._loop = None
            self._stop_event = None
        else:
            self.emit("console", {"message": "services_stop_pending"})

        self._state.node_agent_status = "stopped"
        self._state.runtime_status = "stopped"
        self._state.connected = False
        # Keep registration state sticky across service restarts.
        self._state.registration_status = "registered" if self._state.registered else "not-registered"
        self._state.services_started_at = None
        self._state.runtime_started_at = None
        self._state.current_job_status = "idle"
        self._state.current_job_id = ""
        self._state.touch()

        self.emit("console", {"message": "services_stopped"})
        self._emit_status()

    def start_runtime(self) -> None:
        if self._runtime_enabled:
            self.emit("console", {"message": "runtime_already_running"})
            return

        if not self._services_running:
            self.emit("console", {"message": "runtime_start_info: auto_starting_services"})
            self.start_services()

        if not self._config.consent_accepted:
            self.emit("console", {"message": "runtime_start_blocked: consent_required"})
            self._set_runtime_state("awaiting-registration")
            return

        if self._state.discovery_status == "ineligible" and not self._config.demo_mode:
            self.emit("console", {"message": "runtime_start_blocked: discovery_ineligible"})
            self._set_runtime_state("awaiting-registration")
            return

        self._runtime_enabled = True
        if not self._state.registered or not self._state.node_id:
            self.emit("console", {"message": "runtime_start_info: auto_registration_pending"})
            self._state.runtime_status = "awaiting-registration"
            self._state.runtime_started_at = None
            self._state.touch()
            self._submit_async(self._attempt_auto_register())
            self._emit_status()
            return

        self._state.runtime_status = "starting"
        self._state.runtime_started_at = datetime.now()
        self._state.touch()
        # Ensure claim loop can run immediately (offline nodes cannot claim jobs).
        self._submit_async(self._send_presence_heartbeat(status="healthy", jobs_running=0, event_name="runtime_starting"))
        self.emit("console", {"message": "runtime_start_requested"})
        self._emit_status()

    def stop_runtime(self) -> None:
        if not self._runtime_enabled:
            self.emit("console", {"message": "runtime_already_stopped"})
            return

        self._runtime_enabled = False
        self._state.runtime_status = "stopping"
        self._state.runtime_started_at = None
        self._state.current_job_status = "idle"
        self._state.current_job_id = ""
        self._state.touch()

        if self._loop:
            self._loop.call_soon_threadsafe(self._cancel_job_task)
        if self._services_running and self._state.registered and self._state.node_id:
            self._submit_async(self._send_presence_heartbeat(status="healthy", jobs_running=0, event_name="runtime_stopped"))

        self.emit("console", {"message": "runtime_stop_requested"})
        self._emit_status()

    def refresh_status(self) -> None:
        self._submit_async(self._refresh_status())

    def refresh_distributed_tasks(self) -> None:
        self._submit_async(self._emit_distributed_tasks(force=True))

    def run_discovery(self) -> None:
        self._submit_async(self._run_discovery())

    def fetch_device_details(self) -> None:
        self._submit_async(self._fetch_device_details())

    def register_node(self) -> None:
        node_id, created = self._ensure_local_node_id()
        if created:
            self.emit("console", {"message": f"local_node_id_created={node_id}"})
        if not self._services_running:
            self.start_services()
        self._submit_async(self._register_node(auto=False))

    def submit_test_job(self) -> None:
        self._submit_async(self._submit_test_job())

    def request_models(self) -> None:
        self.emit("console", {"message": "models_disabled: fabric_runtime"})

    def download_model(self, model_name: str) -> None:
        _ = model_name
        self.emit("console", {"message": "model_download_disabled: managed_by_workload_artifacts"})

    def accept_consent(self, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            self.emit("console", {"message": "consent_failed: missing_name"})
            return

        self._config.consent_accepted = True
        self._config.consent_name = cleaned
        self._config.consent_at = datetime.utcnow().isoformat()
        save_config(self._config)

        self._state.consent_status = "accepted"
        self._state.touch()

        self.emit("console", {"message": f"consent_saved_for={cleaned}"})
        self._emit_status()

    def set_demo_mode(self, enabled: bool) -> None:
        self._config.demo_mode = enabled
        save_config(self._config)
        self.emit("console", {"message": f"demo_mode={'on' if enabled else 'off'}"})

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self._queue.put({"type": event_type, "payload": payload or {}})

    def _emit_status(self) -> None:
        self.emit(
            "status",
            {
                "coordinator": self._state.coordinator_status,
                "agent": self._state.node_agent_status,
                "discovery": self._state.discovery_status,
                "registration": self._state.registration_status,
                "runtime": self._state.runtime_status,
                "node_id": self._state.node_id,
                "trust": self._state.trust_score,
            },
        )

    def _run_thread(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        await self._initialize()

        self._status_task = asyncio.create_task(self._status_loop())

        while not self._stop_event.is_set():
            if not self._services_running:
                await self._stop_runtime_tasks()
                self._set_runtime_state("stopped")
                await asyncio.sleep(0.5)
                continue

            if not self._state.registered:
                await self._attempt_auto_register()

            if self._state.registered:
                await self._ensure_heartbeat_task()
            else:
                await self._stop_heartbeat_task()

            if self._runtime_enabled:
                if self._state.registered and self._state.connected:
                    await self._ensure_job_task()
                    self._set_runtime_state("running")
                elif self._state.registered:
                    await self._stop_job_task()
                    self._set_runtime_state("awaiting-services")
                else:
                    await self._stop_job_task()
                    self._set_runtime_state("awaiting-registration")
            else:
                await self._stop_job_task()
                self._set_runtime_state("stopped")

            await asyncio.sleep(0.5)

        await self._stop_runtime_tasks()
        if self._status_task:
            self._status_task.cancel()
            await asyncio.gather(self._status_task, return_exceptions=True)

        await self._shutdown()

    async def _initialize(self) -> None:
        gpu = detect_gpu(self._logger)
        self._state.ram_total_gb = get_system_ram_gb()
        if gpu:
            self._state.gpu_name = gpu.name
            self._state.vram_total_gb = gpu.vram_total_gb
            self._state.vram_used_gb = gpu.vram_used_gb

        self._state.last_event = "initialized"
        self._state.consent_status = "accepted" if self._config.consent_accepted else "pending"
        self._state.node_agent_status = "ok"
        self._state.node_id = self._config.node_id or ""
        self._state.registered = bool(self._state.node_id)
        self._state.registration_status = "registered" if self._state.registered else "not-registered"
        self._state.model_cache = list(self._config.model_cache)
        self._state.touch()

        self._trust = TrustManager(get_trust_path())
        self._state.trust_score = self._trust.score

        self._client = self._create_coordinator_client()
        self._sandbox_runner = DockerSandboxRunner(
            config=ContainerExecutionConfig(
                image=self._config.container_image,
                timeout_sec=self._config.container_timeout_sec,
                cpus=self._config.container_cpus,
                memory_mb=self._config.container_memory_mb,
                enable_gpu=self._config.container_enable_gpu,
                network=self._config.container_network,
                readonly_rootfs=self._config.container_readonly_rootfs,
                pids_limit=self._config.container_pids_limit,
                no_new_privileges=self._config.container_no_new_privileges,
            ),
            logger=self._logger,
        )

        await self._run_discovery(initial=True)
        self._emit_status()

    async def _status_loop(self) -> None:
        while not self._stop_event or not self._stop_event.is_set():
            if not self._services_running:
                await asyncio.sleep(1)
                continue

            ok = await self._check_coordinator_once()
            self._state.coordinator_status = "ok" if ok else "down"
            self._state.connected = ok
            self._state.node_agent_status = "ok"
            self._state.registration_status = "registered" if self._state.registered else "not-registered"
            self._state.touch()
            self._emit_status()
            await self._emit_distributed_tasks(force=False)

            await asyncio.sleep(self.STATUS_POLL_SEC)

    def _create_coordinator_client(self) -> CoordinatorClient:
        return CoordinatorClient(
            base_url=self._config.coordinator_url,
            api_token=self._config.api_token,
            timeout=self._config.request_timeout_sec,
            logger=self._logger,
            node_join_token=self._config.node_join_token,
            node_token=self._config.node_auth_token,
            tls_verify=self._config.tls_verify,
            tls_ca_cert_path=self._config.tls_ca_cert_path,
            tls_client_cert_path=self._config.tls_client_cert_path,
            tls_client_key_path=self._config.tls_client_key_path,
        )

    async def _check_coordinator_once(self) -> bool:
        client = self._client
        temp_client: CoordinatorClient | None = None

        if client is None:
            temp_client = self._create_coordinator_client()
            client = temp_client

        try:
            ok = await client.get_health(self._config.health_endpoint)
        finally:
            if temp_client:
                await temp_client.close()

        return ok

    async def _refresh_status(self) -> None:
        ok = await self._check_coordinator_once()
        self._state.coordinator_status = "ok" if ok else "down"
        self._state.connected = ok
        self._state.registration_status = "registered" if self._state.registered else "not-registered"
        self._state.touch()
        self.emit(
            "console",
            {
                "message": (
                    f"status_refreshed coordinator={'ok' if ok else 'down'} "
                    f"url={self._config.coordinator_url}"
                )
            },
        )
        self._emit_status()

    def _detect_task_mode_from_payload(self, payload: dict[str, Any]) -> str:
        config = payload.get("config")
        if isinstance(config, dict):
            mode = str(config.get("mode") or "").strip().lower()
            if mode in {"train", "finetune", "inference", "evaluation"}:
                return mode

        prompt = str(payload.get("prompt") or "")
        lowered = prompt.lower()
        marker = "workload_mode:"
        if marker in lowered:
            tail = lowered.split(marker, 1)[1].strip()
            candidate = tail.splitlines()[0].strip().split(" ", 1)[0]
            if candidate in {"train", "finetune", "inference", "evaluation"}:
                return candidate

        return "inference"

    async def _emit_distributed_tasks(self, force: bool) -> None:
        if not self._services_running or not self._client or not self._state.connected:
            return

        now = datetime.now()
        if (
            not force
            and self._last_task_snapshot_at is not None
            and (now - self._last_task_snapshot_at).total_seconds() < self.TASK_SNAPSHOT_SEC
        ):
            return
        self._last_task_snapshot_at = now

        try:
            jobs = await self._client.list_jobs(self._config.job_submit_endpoint)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("distributed_tasks_fetch_failed", extra={"error": str(exc)})
            return

        node_id = (self._state.node_id or "").strip()
        counts = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "verifying": 0,
            "completed": 0,
            "failed": 0,
            "assigned_to_node": 0,
        }
        items: list[dict[str, Any]] = []

        for raw in jobs:
            job_id = str(raw.get("id") or "").strip()
            if not job_id:
                continue

            status = str(raw.get("status") or "unknown").strip().lower()
            counts["total"] += 1
            if status in counts:
                counts[status] += 1

            assigned = [str(x) for x in (raw.get("assigned_node_ids") or [])]
            inflight = [str(x) for x in (raw.get("inflight_node_ids") or [])]
            scheduled = [str(x) for x in (raw.get("scheduled_node_ids") or [])]
            failed_ids = [str(x) for x in (raw.get("failed_node_ids") or [])]
            node_related = bool(node_id) and (
                node_id in assigned
                or node_id in inflight
                or node_id in scheduled
                or node_id in failed_ids
            )
            if node_related:
                counts["assigned_to_node"] += 1

            # Keep the node view focused on active network jobs and jobs related to this node.
            if not node_related and status not in {"pending", "running", "verifying"}:
                continue

            prompt = str(raw.get("prompt") or "")
            merged_output = str(raw.get("merged_output") or "")
            try:
                progress = float(raw.get("progress") or 0.0)
            except (TypeError, ValueError):
                progress = 0.0

            items.append(
                {
                    "job_id": job_id,
                    "status": status,
                    "scope": ("assigned" if node_related else "network"),
                    "mode": self._detect_task_mode_from_payload(raw),
                    "progress": max(0.0, min(100.0, progress)),
                    "prompt_preview": prompt.strip().replace("\n", " ")[:240],
                    "result_preview": merged_output.strip().replace("\n", " ")[:240],
                    "updated_at": str(raw.get("updated_at") or ""),
                    "assigned_node_ids": assigned,
                    "inflight_node_ids": inflight,
                }
            )

        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        self.emit(
            "distributed_tasks",
            {
                "node_id": node_id,
                "counts": counts,
                "items": items[:80],
                "updated_at": now.isoformat(),
            },
        )

    def _set_runtime_state(self, value: str) -> None:
        if self._state.runtime_status == value:
            return
        self._state.runtime_status = value
        if value == "running" and self._state.runtime_started_at is None:
            self._state.runtime_started_at = datetime.now()
        if value != "running":
            self._state.runtime_started_at = None
        self._state.touch()
        self._emit_status()

    async def _send_presence_heartbeat(self, status: str, jobs_running: int, event_name: str) -> bool:
        if not self._state.node_id:
            return False

        client = self._client
        temp_client: CoordinatorClient | None = None
        if client is None:
            temp_client = self._create_coordinator_client()
            client = temp_client

        payload = {
            "status": status,
            "vram_used_gb": get_vram_used_gb(self._logger),
            "latency_ms": None,
            "jobs_running": max(0, jobs_running),
            "model_cache": self._state.model_cache,
        }
        endpoint = self._config.heartbeat_endpoint.format(node_id=self._state.node_id)

        try:
            response = await client.heartbeat(endpoint, payload)
            if response is None:
                self._state.registered = False
                self._state.registration_status = "not-registered"
                self._state.last_error = "presence_heartbeat_failed: node_not_registered_remote"
                self._state.last_event = "presence_heartbeat_node_not_registered"
                self._state.touch()
                self._emit_status()
                return False
            self._state.last_heartbeat = datetime.now()
            self._state.last_event = event_name
            self._state.connected = status != "offline"
            self._state.touch()
            self._emit_status()
            return True
        except Exception as exc:  # noqa: BLE001
            self._state.connected = False
            self._state.last_error = f"presence_heartbeat_failed: {exc}"
            self._logger.warning(
                "presence_heartbeat_failed",
                extra={"status": status, "jobs_running": jobs_running, "error": str(exc)},
            )
            self._state.touch()
            self._emit_status()
            return False
        finally:
            if temp_client:
                await temp_client.close()

    async def _ensure_heartbeat_task(self) -> None:
        if not self._client or not self._trust:
            return
        if not self._state.node_id:
            return

        heartbeat_endpoint = self._config.heartbeat_endpoint.format(node_id=self._state.node_id)

        if not self._heartbeat_task or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(
                heartbeat_loop(
                    self._state,
                    self._client,
                    heartbeat_endpoint,
                    self._config.heartbeat_interval_sec,
                    self._stop_event,
                    self._logger,
                )
            )

    async def _ensure_job_task(self) -> None:
        if not self._client or not self._trust:
            return
        if not self._state.node_id:
            return

        heartbeat_endpoint = self._config.heartbeat_endpoint.format(node_id=self._state.node_id)
        claim_endpoint = self._config.job_claim_endpoint.format(node_id=self._state.node_id)
        result_endpoint = self._config.job_result_endpoint.format(node_id=self._state.node_id, job_id="{job_id}")
        fail_endpoint = self._config.job_fail_endpoint.format(node_id=self._state.node_id, job_id="{job_id}")

        if not self._job_task or self._job_task.done():
            self._job_task = asyncio.create_task(
                job_worker_loop(
                    self._state,
                    self._client,
                    None,
                    self._trust,
                    heartbeat_endpoint,
                    claim_endpoint,
                    result_endpoint,
                    fail_endpoint,
                    self._config.job_poll_interval_sec,
                    self._stop_event,
                    self._logger,
                    self._config.auto_download_models,
                    self._config.model_name or DEFAULT_FABRIC_MODEL,
                    "fabric",
                    self._config.execution_mode,
                    self._config.container_fallback_to_local,
                    self._sandbox_runner,
                    self.emit,
                )
            )

    def _cancel_job_task(self) -> None:
        if self._job_task:
            self._job_task.cancel()

    async def _stop_heartbeat_task(self) -> None:
        tasks = [task for task in (self._heartbeat_task,) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._heartbeat_task = None

    async def _stop_job_task(self) -> None:
        tasks = [task for task in (self._job_task,) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._job_task = None

    async def _stop_runtime_tasks(self) -> None:
        tasks = [task for task in (self._heartbeat_task, self._job_task) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._heartbeat_task = None
        self._job_task = None

    async def _attempt_auto_register(self) -> None:
        now = datetime.now()
        if self._last_auto_register_attempt and now - self._last_auto_register_attempt < timedelta(seconds=self.AUTO_REGISTER_BACKOFF_SEC):
            return
        self._last_auto_register_attempt = now
        await self._register_node(auto=True)

    async def _run_discovery(self, initial: bool = False) -> None:
        snapshot, debug = collect_device_snapshot(self._state.node_id)
        self._apply_snapshot(snapshot)

        eligible, reason = self._evaluate_eligibility(snapshot)
        snapshot["eligible"] = eligible
        snapshot["eligibility_reason"] = reason
        snapshot["capability_message"] = (
            "Capable for Hyperlooms workloads."
            if eligible
            else f"Not capable for Hyperlooms workloads (reason: {reason})."
        )
        self._state.discovery_status = "eligible" if eligible else "ineligible"
        self._state.eligibility_reason = reason
        self._state.touch()

        self.emit(
            "device_details",
            {
                "snapshot": format_snapshot(snapshot),
                "debug": format_debug_trace(debug),
            },
        )

        if not initial:
            self.emit("console", {"message": f"discovery_done eligible={eligible} reason={reason}"})
        self._emit_status()

    async def _fetch_device_details(self) -> None:
        snapshot, debug = collect_device_snapshot(self._state.node_id)
        self._apply_snapshot(snapshot)
        eligible, reason = self._evaluate_eligibility(snapshot)
        snapshot["eligible"] = eligible
        snapshot["eligibility_reason"] = reason
        snapshot["capability_message"] = (
            "Capable for Hyperlooms workloads."
            if eligible
            else f"Not capable for Hyperlooms workloads (reason: {reason})."
        )
        self._state.discovery_status = "eligible" if eligible else "ineligible"
        self._state.eligibility_reason = reason
        self._state.touch()

        self.emit(
            "device_details",
            {
                "snapshot": format_snapshot(snapshot),
                "debug": format_debug_trace(debug),
            },
        )
        self.emit("console", {"message": "device_details_fetched"})
        self._emit_status()

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._state.cpu_model = str(snapshot.get("cpu_model", "Unknown"))
        self._state.cpu_physical = int(snapshot.get("cpu_physical", 0) or 0)
        self._state.cpu_logical = int(snapshot.get("cpu_logical", 0) or 0)
        self._state.ram_total_gb = float(snapshot.get("ram_total_gb", 0.0) or 0.0)
        self._state.ram_free_gb = float(snapshot.get("ram_free_gb", 0.0) or 0.0)
        self._state.disk_total_gb = float(snapshot.get("disk_total_gb", 0.0) or 0.0)
        self._state.disk_free_gb = float(snapshot.get("disk_free_gb", 0.0) or 0.0)
        self._state.gpu_name = str(snapshot.get("gpu_model", "Unknown"))
        self._state.vram_total_gb = float(snapshot.get("vram_total_gb", 0.0) or 0.0)
        self._state.vram_used_gb = float(snapshot.get("vram_used_gb", 0.0) or 0.0)
        self._state.touch()

    async def _register_node(self, auto: bool) -> None:
        if not self._config.consent_accepted:
            self._state.consent_status = "pending"
            if not auto:
                self.emit("console", {"message": "register_failed: consent_required"})
            self._emit_status()
            return

        if self._state.discovery_status == "ineligible" and not self._config.demo_mode:
            if not auto:
                self.emit("console", {"message": "register_failed: discovery_ineligible"})
            self._emit_status()
            return

        coordinator_ok = await self._check_coordinator_once()
        self._state.coordinator_status = "ok" if coordinator_ok else "down"
        self._state.connected = coordinator_ok
        if not coordinator_ok:
            if not auto:
                self.emit(
                    "console",
                    {"message": f"register_failed: coordinator_unreachable url={self._config.coordinator_url}"},
                )
            self._emit_status()
            return

        if not self._client:
            self._client = self._create_coordinator_client()
        else:
            self._client.set_node_join_token(self._config.node_join_token)
            self._client.set_node_token(self._config.node_auth_token)

        node_id, _ = self._ensure_local_node_id()
        gpu_name = self._state.gpu_name or "CPU"
        vram_total = self._state.vram_total_gb if self._state.vram_total_gb > 0 else 1.0

        if self._config.demo_mode:
            gpu_name = "CPU"
            vram_total = 1.0

        model_cache = await self._collect_model_cache()

        payload = {
            "id": node_id,
            "gpu": gpu_name,
            "vram_total_gb": vram_total,
            "region": self._config.region,
            "model_cache": model_cache,
        }

        response: dict[str, Any] | None = None
        register_error = ""
        try:
            response = await self._client.register_node(self._config.register_endpoint, payload)
        except Exception as exc:  # noqa: BLE001
            register_error = str(exc)
            self._state.last_error = f"register_failed: {register_error}"
            self._logger.warning("register_failed", extra={"error": register_error})

        registered_node: dict[str, Any] = {}
        if response:
            if isinstance(response.get("node"), dict):
                registered_node = response["node"]
            else:
                registered_node = response
        if registered_node.get("id"):
            node_id = str(registered_node["id"])

        issued_token = str(response.get("node_token", "")).strip() if response else ""
        if issued_token:
            self._config.node_auth_token = issued_token
            self._config.node_auth_token_expires_at = str(response.get("token_expires_at", "")).strip()
            if self._client:
                self._client.set_node_token(issued_token)

        registered = response is not None
        self._state.node_id = node_id
        self._state.registered = registered
        self._state.registration_status = "registered" if registered else "not-registered"
        self._state.connected = coordinator_ok
        self._state.last_event = "node_registered" if registered else "node_register_failed"
        self._state.model_cache = model_cache
        self._state.touch()

        if self._config.node_id != node_id or issued_token:
            self._config.node_id = node_id
            self._config.model_cache = model_cache
            save_config(self._config)

        if not auto:
            if registered:
                self.emit("console", {"message": f"registered node_id={node_id}"})
            else:
                details = f" error={register_error}" if register_error else ""
                self.emit("console", {"message": f"register_failed{details}"})

        if registered and self._services_running:
            await self._send_presence_heartbeat(status="healthy", jobs_running=0, event_name="post_register_services_online")

        self._emit_status()
        if self._services_running:
            await self._emit_distributed_tasks(force=True)

    def _ensure_local_node_id(self) -> tuple[str, bool]:
        existing = (self._config.node_id or self._state.node_id or "").strip()
        if existing:
            self._state.node_id = existing
            self._state.touch()
            return existing, False

        node_id = f"node-{uuid4().hex[:10]}"
        self._config.node_id = node_id
        save_config(self._config)
        self._state.node_id = node_id
        self._state.registration_status = "not-registered"
        self._state.last_event = "node_id_provisioned"
        self._state.touch()
        self._emit_status()
        return node_id, True

    async def _submit_test_job(self) -> None:
        client = self._client
        temp_client: CoordinatorClient | None = None
        if client is None:
            temp_client = self._create_coordinator_client()
            client = temp_client

        chosen_model = self._config.model_name or DEFAULT_FABRIC_MODEL

        payload = {
            "prompt": "Hyperlooms node test job",
            "config": {
                "model": chosen_model,
                "temperature": 0.2,
                "max_tokens": 256,
                "provider": "fabric",
            },
        }

        response: dict[str, Any] | None = None
        try:
            response = await client.submit_job(self._config.job_submit_endpoint, payload)
        except Exception as exc:  # noqa: BLE001
            self.emit(
                "console",
                {"message": f"submit_job_failed error={exc} url={self._config.coordinator_url}"},
            )

        if temp_client:
            await temp_client.close()

        if response and response.get("id"):
            self.emit("console", {"message": f"test_job_submitted id={response.get('id')}"})
        else:
            self.emit("console", {"message": "test_job_submit_failed"})

    async def _shutdown(self) -> None:
        await self._stop_runtime_tasks()

        if self._client:
            await self._client.close()
            self._client = None
        self._sandbox_runner = None

        known_node_id = self._config.node_id or self._state.node_id
        registered = bool(known_node_id)
        self._state.connected = False
        self._state.registered = registered
        self._state.node_id = known_node_id or ""
        self._state.registration_status = "registered" if registered else "not-registered"
        self._state.node_agent_status = "stopped"
        self._state.runtime_status = "stopped"
        self._state.current_job_status = "idle"
        self._state.current_job_id = ""
        self._state.last_event = "stopped"
        self._state.touch()
        self._emit_status()
        self.emit("console", {"message": "agent_stopped"})

    def _evaluate_eligibility(self, snapshot: dict[str, Any]) -> tuple[bool, str]:
        if self._config.demo_mode:
            return True, "demo_mode"
        if self._config.require_gpu and not snapshot.get("gpu_present"):
            return False, "gpu_missing"
        if float(snapshot.get("vram_total_gb", 0.0) or 0.0) < self._config.min_vram_gb:
            return False, "low_vram"
        if float(snapshot.get("ram_total_gb", 0.0) or 0.0) < self._config.min_ram_gb:
            return False, "low_ram"
        if float(snapshot.get("disk_total_gb", 0.0) or 0.0) < self._config.min_disk_gb:
            return False, "low_disk"
        return True, "ok"

    def _submit_async(self, coro: Coroutine[Any, Any, Any]) -> None:
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)

            def _done_callback(done_future) -> None:
                try:
                    done_future.result()
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning("async_task_failed", extra={"error": str(exc)})
                    self.emit("console", {"message": f"task_failed error={exc}"})

            future.add_done_callback(_done_callback)
            return

        # Fallback for one-off actions before services start.
        def _runner() -> None:
            try:
                asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("adhoc_async_failed", extra={"error": str(exc)})
                self.emit("console", {"message": f"task_failed error={exc}"})

        threading.Thread(target=_runner, daemon=True).start()

    async def _fetch_models(self) -> None:
        self.emit("models", {"items": []})

    async def _download_model(self, model_name: str) -> None:
        _ = model_name
        self.emit("model_download_failed", {"model": "", "error": "disabled_in_fabric_runtime"})

    async def _collect_model_cache(self) -> list[str]:
        items: list[str] = []
        items.extend(self._config.model_cache)
        if self._config.model_name:
            items.append(self._config.model_name)
        else:
            items.append(DEFAULT_FABRIC_MODEL)

        normalized = self._normalize_models(items)
        self._config.model_cache = normalized
        self._state.model_cache = normalized
        return normalized

    def _normalize_models(self, models: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in models:
            cleaned = str(item).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(cleaned)
        return unique[-32:]
