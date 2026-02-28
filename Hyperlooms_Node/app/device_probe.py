from __future__ import annotations

from datetime import datetime
import os
import platform
import subprocess
from typing import Any

import psutil

from app.gpu_detector import detect_gpu


def _run_cmd(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _parse_wmic_list(output: str) -> list[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if lines and lines[0].lower().startswith("name"):
        lines = lines[1:]
    return lines


def _cpu_model() -> str:
    output = _run_cmd(["wmic", "cpu", "get", "name"])
    lines = _parse_wmic_list(output)
    return lines[0] if lines else (platform.processor() or "Unknown")


def _gpu_models() -> list[str]:
    output = _run_cmd(["wmic", "path", "win32_VideoController", "get", "name"])
    return _parse_wmic_list(output)


def _gpu_vendor(model: str) -> str:
    lower = model.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "amd" in lower or "radeon" in lower:
        return "amd"
    if "intel" in lower:
        return "intel"
    return "unknown"


def collect_device_snapshot(node_id: str | None = None) -> tuple[dict[str, Any], list[str]]:
    debug: list[str] = []
    debug.append(f"platform={platform.platform()}")
    debug.append(f"python={platform.python_version()}")

    cpu_model = _cpu_model()
    cpu_physical = psutil.cpu_count(logical=False) or 0
    cpu_logical = psutil.cpu_count(logical=True) or 0

    memory = psutil.virtual_memory()
    ram_total = round(memory.total / (1024**3), 2)
    ram_free = round(memory.available / (1024**3), 2)
    debug.append(f"memory_probe=total_gb={ram_total} free_gb={ram_free}")

    drive = os.getenv("SystemDrive", "C:")
    drive_path = drive + "\\"
    disk_usage = psutil.disk_usage(drive_path)
    disk_total = round(disk_usage.total / (1024**3), 2)
    disk_free = round(disk_usage.free / (1024**3), 2)
    debug.append(f"disk_probe=total_gb={disk_total} free_gb={disk_free}")

    gpu_info = detect_gpu()
    gpu_models = _gpu_models()
    gpu_present = bool(gpu_models) or (gpu_info is not None)

    gpu_model = gpu_info.name if gpu_info else (gpu_models[0] if gpu_models else "None")
    vram_total = gpu_info.vram_total_gb if gpu_info else 0.0
    vram_used = gpu_info.vram_used_gb if gpu_info else 0.0

    compute_capability = "None"
    cuda_available = False
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            capability = torch.cuda.get_device_capability(0)
            compute_capability = f"{capability[0]}.{capability[1]}"
    except Exception:
        debug.append("gpu_detector=torch:none")
    else:
        debug.append("gpu_detector=torch:cuda" if cuda_available else "gpu_detector=torch:present")

    if gpu_models:
        debug.append("gpu_detector=windows-cim")

    snapshot = {
        "node_id": node_id or "-",
        "collected_at": datetime.utcnow().isoformat(),
        "cpu_model": cpu_model,
        "cpu_physical": cpu_physical,
        "cpu_logical": cpu_logical,
        "ram_total_gb": ram_total,
        "ram_free_gb": ram_free,
        "disk_total_gb": disk_total,
        "disk_free_gb": disk_free,
        "gpu_present": gpu_present,
        "gpu_vendor": _gpu_vendor(gpu_model),
        "gpu_model": gpu_model,
        "vram_total_gb": vram_total,
        "vram_used_gb": vram_used,
        "compute_capability": compute_capability,
        "cuda_available": cuda_available,
        "rocm_available": False,
    }
    return snapshot, debug


def format_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        f"Node ID: {snapshot.get('node_id', '-')}",
        f"Collected At: {snapshot.get('collected_at', '-')}",
        "",
        f"CPU Model: {snapshot.get('cpu_model', 'Unknown')}",
        f"CPU Cores: physical={snapshot.get('cpu_physical', 0)} logical={snapshot.get('cpu_logical', 0)}",
        f"RAM: total={snapshot.get('ram_total_gb', 0)} GB free={snapshot.get('ram_free_gb', 0)} GB",
        f"Disk: total={snapshot.get('disk_total_gb', 0)} GB free={snapshot.get('disk_free_gb', 0)} GB",
        "",
        f"GPU Present: {snapshot.get('gpu_present', False)}",
        f"GPU Vendor: {snapshot.get('gpu_vendor', 'unknown')}",
        f"GPU Model: {snapshot.get('gpu_model', 'None')}",
        f"VRAM: used={snapshot.get('vram_used_gb', 0)} GB total={snapshot.get('vram_total_gb', 0)} GB",
        f"Compute Capability: {snapshot.get('compute_capability', 'None')}",
        f"CUDA Available: {snapshot.get('cuda_available', False)}",
        f"ROCm Available: {snapshot.get('rocm_available', False)}",
    ]

    capability_message = str(snapshot.get("capability_message", "") or "").strip()
    if capability_message:
        lines.extend(["", f"Capability Check: {capability_message}"])
    return "\n".join(lines)


def format_debug_trace(lines: list[str]) -> str:
    return "\n".join(lines)
