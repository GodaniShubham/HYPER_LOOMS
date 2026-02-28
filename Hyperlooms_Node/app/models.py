from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GPUInfo:
    name: str
    vram_total_gb: float
    vram_used_gb: float


@dataclass
class JobPayload:
    id: str
    prompt: str
    model: str
    provider: str = "auto"
    assignment_hash_key: str = ""
    assignment_expires_at: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
