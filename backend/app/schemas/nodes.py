from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.domain import NodeStatus


class NodeRegisterRequest(BaseModel):
    node_id: str | None = None
    gpu: str
    vram_gb: int = Field(ge=4, le=256)
    trust: float = Field(default=0.7, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeHeartbeatRequest(BaseModel):
    utilization: float = Field(default=0.0, ge=0.0, le=100.0)
    active_jobs: int = Field(default=0, ge=0)
    status: NodeStatus | None = None


class NodeResponse(BaseModel):
    id: str
    gpu: str
    vram_gb: int
    trust: float
    status: NodeStatus
    active_jobs: int
    utilization: float
    created_at: datetime
    updated_at: datetime
    last_heartbeat_at: datetime
    metadata: dict[str, Any]

