from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentState:
    connected: bool = False
    registered: bool = False
    node_id: str = ""

    gpu_name: str = "Unknown"
    vram_total_gb: float = 0.0
    vram_used_gb: float = 0.0

    ram_total_gb: float = 0.0
    ram_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    cpu_model: str = "Unknown"
    cpu_physical: int = 0
    cpu_logical: int = 0

    last_heartbeat: datetime | None = None
    trust_score: float = 0.9

    current_job_id: str = ""
    current_job_status: str = "idle"

    last_error: str = ""
    last_event: str = ""
    last_updated: datetime | None = None

    coordinator_status: str = "unknown"
    node_agent_status: str = "stopped"
    discovery_status: str = "unknown"
    registration_status: str = "not-registered"
    runtime_status: str = "stopped"
    consent_status: str = "pending"
    eligibility_reason: str = ""

    services_started_at: datetime | None = None
    runtime_started_at: datetime | None = None
    model_cache: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.last_updated = datetime.now()
