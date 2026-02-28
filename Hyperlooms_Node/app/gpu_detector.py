from __future__ import annotations

from dataclasses import dataclass
import csv
import logging
import subprocess

import psutil


@dataclass
class GPUInfo:
    name: str
    vram_total_gb: float
    vram_used_gb: float


def _run_command(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _detect_gpu_from_torch(logger: logging.Logger | None = None) -> GPUInfo | None:
    try:
        import torch
    except Exception as exc:
        if logger:
            logger.warning("torch_not_available", extra={"error": str(exc)})
        return None

    try:
        if not torch.cuda.is_available():
            return None

        device_index = 0
        name = torch.cuda.get_device_name(device_index)
        props = torch.cuda.get_device_properties(device_index)
        total_gb = props.total_memory / (1024**3)
        used_gb = torch.cuda.memory_reserved(device_index) / (1024**3)

        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(device_index)
            total_gb = total_bytes / (1024**3)
            used_gb = max(0.0, (total_bytes - free_bytes) / (1024**3))
        except Exception:
            pass

        return GPUInfo(name=name, vram_total_gb=round(total_gb, 2), vram_used_gb=round(used_gb, 2))
    except Exception as exc:
        if logger:
            logger.warning("gpu_detect_failed", extra={"error": str(exc)})
        return None


def _detect_gpu_from_nvidia_smi(logger: logging.Logger | None = None) -> GPUInfo | None:
    output = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return None

    first_line = output.splitlines()[0].strip()
    columns = [item.strip() for item in first_line.split(",")]
    if len(columns) < 3:
        return None

    try:
        total_mb = float(columns[1])
        used_mb = float(columns[2])
    except ValueError:
        if logger:
            logger.warning("nvidia_smi_parse_failed", extra={"line": first_line})
        return None

    return GPUInfo(
        name=columns[0] or "NVIDIA GPU",
        vram_total_gb=round(total_mb / 1024, 2),
        vram_used_gb=round(used_mb / 1024, 2),
    )


def _detect_gpu_from_wmic(logger: logging.Logger | None = None) -> GPUInfo | None:
    output = _run_command(["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"])
    if not output:
        return None

    rows = [line for line in output.splitlines() if line.strip()]
    if len(rows) < 2:
        return None

    candidates: list[tuple[int, str]] = []
    try:
        for row in csv.DictReader(rows):
            name = (row.get("Name") or "").strip()
            raw_adapter_ram = (row.get("AdapterRAM") or "").strip()
            if not name or not raw_adapter_ram:
                continue
            adapter_ram = int(raw_adapter_ram)
            if adapter_ram <= 0:
                continue
            candidates.append((adapter_ram, name))
    except Exception as exc:
        if logger:
            logger.warning("wmic_gpu_parse_failed", extra={"error": str(exc)})
        return None

    if not candidates:
        return None

    adapter_ram, name = max(candidates, key=lambda item: item[0])
    return GPUInfo(
        name=name,
        vram_total_gb=round(adapter_ram / (1024**3), 2),
        vram_used_gb=0.0,
    )


def detect_gpu(logger: logging.Logger | None = None) -> GPUInfo | None:
    gpu = _detect_gpu_from_torch(logger)
    if gpu:
        return gpu

    gpu = _detect_gpu_from_nvidia_smi(logger)
    if gpu:
        return gpu

    gpu = _detect_gpu_from_wmic(logger)
    if gpu:
        return gpu

    return None


def get_vram_used_gb(logger: logging.Logger | None = None) -> float:
    gpu = _detect_gpu_from_nvidia_smi(logger)
    if gpu:
        return gpu.vram_used_gb

    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0

        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(0)
            used_gb = max(0.0, (total_bytes - free_bytes) / (1024**3))
        except Exception:
            used_gb = torch.cuda.memory_reserved(0) / (1024**3)

        return round(used_gb, 2)
    except Exception as exc:
        if logger:
            logger.warning("gpu_vram_query_failed", extra={"error": str(exc)})
        return 0.0


def get_system_ram_gb() -> float:
    return round(psutil.virtual_memory().total / (1024**3), 2)
