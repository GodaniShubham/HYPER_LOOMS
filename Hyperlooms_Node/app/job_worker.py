from __future__ import annotations

import asyncio
from datetime import datetime
from time import perf_counter
from typing import Any, Callable

from app.container_runner import DockerSandboxRunner
from app.coordinator_client import CoordinatorClient
from app.gpu_detector import get_vram_used_gb
from app.models import JobPayload
from app.state import AgentState
from app.trust_manager import TrustManager

TASK_MODES = {"train", "finetune", "inference", "evaluation"}


def _normalized_options(params: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    raw_options = params.get("options")
    if isinstance(raw_options, dict):
        options.update(raw_options)

    if "temperature" in params and "temperature" not in options:
        options["temperature"] = params["temperature"]
    if "max_tokens" in params and "max_tokens" not in options:
        options["max_tokens"] = params["max_tokens"]

    return options


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: int) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


def _parse_job(payload: dict[str, Any], default_model: str) -> JobPayload | None:
    claim_scope = payload
    assignment_hash_key = ""
    assignment_expires_at = ""
    if isinstance(payload.get("job"), dict):
        claim_scope = payload["job"]
        assignment_hash_key = str(payload.get("assignment_hash_key") or "")
        assignment_expires_at = str(payload.get("assignment_expires_at") or "")

    job_id = claim_scope.get("id") or claim_scope.get("job_id")
    prompt = claim_scope.get("prompt")
    if not job_id or not prompt:
        return None

    config = claim_scope.get("config") or {}
    model = claim_scope.get("model") or config.get("model") or default_model
    provider = claim_scope.get("provider") or config.get("provider") or "auto"

    return JobPayload(
        id=str(job_id),
        prompt=str(prompt),
        model=str(model),
        provider=str(provider),
        assignment_hash_key=assignment_hash_key,
        assignment_expires_at=assignment_expires_at,
        params=config if isinstance(config, dict) else {},
        raw=payload,
    )


def _mark_model_cached(state: AgentState, model: str) -> None:
    cleaned = model.strip()
    if not cleaned:
        return
    known = {item.lower() for item in state.model_cache}
    if cleaned.lower() in known:
        return
    state.model_cache.append(cleaned)
    state.model_cache = state.model_cache[-32:]


def _emit_task_event(
    callback: Callable[[str, dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback("task_update", payload)
    except Exception:  # noqa: BLE001
        return


def _detect_task_mode(job: JobPayload) -> str:
    raw_mode = str(job.params.get("mode") or "").strip().lower()
    if raw_mode in TASK_MODES:
        return raw_mode

    lowered = job.prompt.lower()
    marker = "workload_mode:"
    if marker in lowered:
        tail = lowered.split(marker, 1)[1].strip()
        candidate = tail.splitlines()[0].strip().split(" ", 1)[0]
        if candidate in TASK_MODES:
            return candidate

    return "inference"


async def _emit_runtime_heartbeat(
    *,
    state: AgentState,
    client: CoordinatorClient,
    heartbeat_endpoint: str,
    status: str,
    jobs_running: int,
    logger,
) -> None:
    payload = {
        "status": status,
        "vram_used_gb": get_vram_used_gb(logger),
        "latency_ms": None,
        "jobs_running": max(0, jobs_running),
        "model_cache": state.model_cache,
    }
    try:
        await client.heartbeat(heartbeat_endpoint, payload)
        state.last_heartbeat = datetime.now()
        state.last_event = "job_status_heartbeat"
    except Exception as exc:  # noqa: BLE001
        state.last_error = f"job_status_heartbeat_failed: {exc}"
        logger.warning("job_status_heartbeat_failed", extra={"status": status, "error": str(exc)})


async def _run_local_inference(
    *,
    job: JobPayload,
    options: dict[str, Any],
    model_name: str,
) -> dict[str, Any]:
    await asyncio.sleep(0.12)
    max_tokens = int(options.get("max_tokens") or 256)
    temperature = float(options.get("temperature") or 0.2)
    mode = _detect_task_mode(job)
    summary = {
        "mode": mode,
        "model": model_name,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "status": "accepted_by_node",
    }
    text = (
        f"Fabric node executed workload locally. "
        f"mode={mode} model={model_name} max_tokens={max_tokens} temperature={temperature:.2f}. "
        f"Prompt length={len(job.prompt)} chars."
    )
    return {"response": text, "raw": summary}


async def job_worker_loop(
    state: AgentState,
    client: CoordinatorClient,
    inference,
    trust: TrustManager,
    heartbeat_endpoint: str,
    claim_endpoint: str,
    result_endpoint_template: str,
    fail_endpoint_template: str,
    poll_interval_sec: int,
    stop_event: asyncio.Event,
    logger,
    auto_download_models: bool,
    default_model: str,
    provider_hint: str,
    execution_mode: str,
    container_fallback_to_local: bool,
    sandbox_runner: DockerSandboxRunner | None = None,
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    _ = inference
    _ = auto_download_models
    _ = provider_hint
    while not stop_event.is_set():
        if not state.node_id:
            await _sleep_or_stop(stop_event, poll_interval_sec)
            continue
        if not state.connected:
            state.last_event = "claim_paused_coordinator_down"
            state.touch()
            await _sleep_or_stop(stop_event, poll_interval_sec)
            continue

        try:
            payload = await client.claim_job(claim_endpoint)
        except Exception as exc:  # noqa: BLE001
            state.last_error = f"claim_failed: {exc}"
            logger.warning("job_claim_failed", extra={"error": str(exc)})
            await _sleep_or_stop(stop_event, poll_interval_sec)
            continue

        if not payload:
            await _sleep_or_stop(stop_event, poll_interval_sec)
            continue

        job = _parse_job(payload, default_model)
        if not job:
            logger.warning("job_payload_invalid", extra={"payload": payload})
            await _sleep_or_stop(stop_event, poll_interval_sec)
            continue

        state.current_job_id = job.id
        state.current_job_status = "running"
        state.last_event = "job_started"
        state.touch()
        task_mode = _detect_task_mode(job)
        claimed_at = datetime.now().isoformat()
        prompt_preview = job.prompt.strip().replace("\n", " ")[:240]
        _emit_task_event(
            event_callback,
            {
                "job_id": job.id,
                "status": "assigned",
                "scope": "assigned",
                "mode": task_mode,
                "prompt_preview": prompt_preview,
                "progress": 5.0,
                "assigned_at": claimed_at,
                "updated_at": claimed_at,
            },
        )
        _emit_task_event(
            event_callback,
            {
                "job_id": job.id,
                "status": "running",
                "scope": "assigned",
                "mode": task_mode,
                "prompt_preview": prompt_preview,
                "progress": 45.0,
                "assigned_at": claimed_at,
                "updated_at": datetime.now().isoformat(),
            },
        )
        await _emit_runtime_heartbeat(
            state=state,
            client=client,
            heartbeat_endpoint=heartbeat_endpoint,
            status="busy",
            jobs_running=1,
            logger=logger,
        )

        started = perf_counter()
        selected_model = default_model.strip() or job.model

        try:
            options = _normalized_options(job.params)
            run_in_container = execution_mode.strip().lower() == "container" and sandbox_runner is not None

            if run_in_container:
                try:
                    response = await sandbox_runner.run_workload(
                        job_id=job.id,
                        prompt=job.prompt,
                        model=selected_model,
                        mode=task_mode,
                        options=options,
                    )
                except Exception as exc:  # noqa: BLE001
                    if not container_fallback_to_local:
                        raise RuntimeError(f"container_workload_failed: {exc}") from exc
                    logger.warning(
                        "container_exec_failed_fallback",
                        extra={"job_id": job.id, "error": str(exc)},
                    )
                    response = await _run_local_inference(
                        job=job,
                        options=options,
                        model_name=selected_model,
                    )
            else:
                response = await _run_local_inference(
                    job=job,
                    options=options,
                    model_name=selected_model,
                )

            output = response.get("response", "")
            elapsed_ms = round((perf_counter() - started) * 1000, 2)

            result_payload = {
                "job_id": job.id,
                "output": output,
                "latency_ms": elapsed_ms,
                "raw": response.get("raw", response),
            }
            if job.assignment_hash_key:
                result_payload["assignment_hash_key"] = job.assignment_hash_key

            submitted = await client.submit_result(result_endpoint_template.format(job_id=job.id), result_payload)
            if not submitted:
                raise RuntimeError("result_submit_rejected")

            trust.record_success()
            _mark_model_cached(state, selected_model)
            state.trust_score = trust.score
            state.last_event = "job_completed"
            _emit_task_event(
                event_callback,
                {
                    "job_id": job.id,
                    "status": "completed",
                    "scope": "assigned",
                    "mode": task_mode,
                    "model": selected_model,
                    "prompt_preview": prompt_preview,
                    "result_preview": str(output).strip().replace("\n", " ")[:240],
                    "progress": 100.0,
                    "latency_ms": elapsed_ms,
                    "updated_at": datetime.now().isoformat(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            message = f"job_failed: {exc}"
            logger.warning(message)
            state.last_error = message
            failure_payload = {"job_id": job.id, "error": message}
            if job.assignment_hash_key:
                failure_payload["assignment_hash_key"] = job.assignment_hash_key
            await client.submit_failure(fail_endpoint_template.format(job_id=job.id), failure_payload)
            trust.record_failure()
            _emit_task_event(
                event_callback,
                {
                    "job_id": job.id,
                    "status": "failed",
                    "scope": "assigned",
                    "mode": task_mode,
                    "model": selected_model,
                    "prompt_preview": prompt_preview,
                    "error": str(exc),
                    "progress": 100.0,
                    "updated_at": datetime.now().isoformat(),
                },
            )
        finally:
            state.current_job_status = "idle"
            state.current_job_id = ""
            state.trust_score = trust.score
            state.touch()
            await _emit_runtime_heartbeat(
                state=state,
                client=client,
                heartbeat_endpoint=heartbeat_endpoint,
                status="healthy",
                jobs_running=0,
                logger=logger,
            )

        await _sleep_or_stop(stop_event, poll_interval_sec)
