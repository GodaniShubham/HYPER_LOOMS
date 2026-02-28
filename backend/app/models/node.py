from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NodeStatus(StrEnum):
    healthy = "healthy"
    busy = "busy"
    offline = "offline"


class Node(BaseModel):
    id: str = Field(default_factory=lambda: f"node-{uuid4().hex[:10]}")
    gpu: str
    vram_total_gb: float = Field(gt=0)
    vram_used_gb: float = Field(default=0, ge=0)
    status: NodeStatus = NodeStatus.healthy
    trust_score: float = Field(default=0.9, ge=0.0, le=1.0)
    jobs_running: int = Field(default=0, ge=0)
    latency_ms_avg: float = Field(default=0, ge=0)
    region: str = "us-east-1"
    model_cache: list[str] = Field(default_factory=list)
    last_heartbeat: datetime = Field(default_factory=utc_now)

    @property
    def free_vram_gb(self) -> float:
        return max(0, self.vram_total_gb - self.vram_used_gb)


class NodeRegisterRequest(BaseModel):
    id: str | None = None
    gpu: str = Field(min_length=2, max_length=64)
    vram_total_gb: float = Field(gt=0)
    region: str = Field(default="us-east-1", min_length=2, max_length=64)
    model_cache: list[str] = Field(default_factory=list)


class NodeHeartbeatRequest(BaseModel):
    status: NodeStatus | None = None
    vram_used_gb: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    jobs_running: int | None = Field(default=None, ge=0)
    model_cache: list[str] | None = None


class NodeListResponse(BaseModel):
    items: list[Node]


class NodeRegisterResponse(BaseModel):
    node: Node
    node_token: str | None = None
    token_expires_at: datetime | None = None
