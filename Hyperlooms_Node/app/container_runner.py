from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from uuid import uuid4


class ContainerExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class ContainerExecutionConfig:
    image: str
    timeout_sec: int
    cpus: float
    memory_mb: int
    enable_gpu: bool
    network: str
    readonly_rootfs: bool
    pids_limit: int
    no_new_privileges: bool


def _sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower())
    return cleaned[:20] or "job"


class DockerSandboxRunner:
    def __init__(self, config: ContainerExecutionConfig, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger

    async def run_workload(
        self,
        *,
        job_id: str,
        prompt: str,
        model: str,
        mode: str,
        options: dict,
    ) -> dict:
        payload = {
            "job_id": job_id,
            "prompt": prompt,
            "model": model,
            "mode": mode,
            "options": options,
        }
        payload_raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_raw).decode("ascii")

        container_name = f"cf-sbx-{_sanitize_name(job_id)}-{uuid4().hex[:6]}"
        command = self._build_command(container_name=container_name, payload_b64=payload_b64)

        self._logger.info(
            "container_exec_start",
            extra={"job_id": job_id, "container_name": container_name, "image": self._config.image},
        )

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=max(30, self._config.timeout_sec))
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise ContainerExecutionError("container_workload_timeout") from exc

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            tail = stderr_text[-1200:] if stderr_text else stdout_text[-1200:]
            raise ContainerExecutionError(f"container_workload_failed(rc={proc.returncode}): {tail}")

        try:
            parsed = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise ContainerExecutionError(f"container_output_invalid_json: {stdout_text[-500:]}") from exc

        if not isinstance(parsed, dict):
            raise ContainerExecutionError("container_output_invalid_shape")
        return parsed


    def _build_command(self, *, container_name: str, payload_b64: str) -> list[str]:
        cfg = self._config
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--cpus",
            str(max(0.5, cfg.cpus)),
            "--memory",
            f"{max(256, cfg.memory_mb)}m",
            "--pids-limit",
            str(max(64, cfg.pids_limit)),
            "--network",
            cfg.network or "bridge",
            "--cap-drop",
            "ALL",
        ]
        if cfg.readonly_rootfs:
            cmd.append("--read-only")
            cmd.extend(["--tmpfs", "/tmp:rw,noexec,nosuid,size=256m"])
        if cfg.no_new_privileges:
            cmd.extend(["--security-opt", "no-new-privileges:true"])
        if cfg.enable_gpu:
            cmd.extend(["--gpus", "all"])
        cmd.extend(
            [
                "-e",
                f"JOB_PAYLOAD_B64={payload_b64}",
                cfg.image,
            ]
        )
        return cmd
