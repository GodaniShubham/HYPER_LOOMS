from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    healthy = "healthy"
    busy = "busy"
    offline = "offline"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    verifying = "verifying"
    completed = "completed"
    failed = "failed"


class Node(BaseModel):
    id: str
    gpu: str
    vram_gb: int
    trust: float = 0.7
    status: NodeStatus = NodeStatus.healthy
    active_jobs: int = 0
    utilization: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobConfig(BaseModel):
    model: str = "llama3.1-70b"
    replicas: int = 2
    max_tokens: int = 512


class JobLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: str = "info"
    message: str


class NodeExecutionResult(BaseModel):
    node_id: str
    output: str
    latency_ms: int
    success: bool = True


class VerificationSummary(BaseModel):
    passed: bool
    confidence: float
    consensus_output: str
    details: dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    id: str
    prompt: str
    status: JobStatus = JobStatus.pending
    config: JobConfig
    assigned_nodes: list[str] = Field(default_factory=list)
    node_results: list[NodeExecutionResult] = Field(default_factory=list)
    verification: VerificationSummary | None = None
    final_output: str | None = None
    logs: list[JobLogEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latency_ms: int | None = None
    error: str | None = None

