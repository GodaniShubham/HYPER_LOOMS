from datetime import datetime

from pydantic import BaseModel

from app.models.job import JobStatus, VerificationStatus
from app.models.node import NodeStatus


class NetworkStatsResponse(BaseModel):
    active_nodes: int
    total_vram_gb: int
    jobs_running: int
    avg_latency_ms: float


class NodeJobDistributionItem(BaseModel):
    node_id: str
    jobs: int
    status: NodeStatus
    trust_score: float


class NodeJobDistributionResponse(BaseModel):
    items: list[NodeJobDistributionItem]


# Backwards-compatible aliases (if any older callers still use these names).
JobDistributionItem = NodeJobDistributionItem
JobDistributionResponse = NodeJobDistributionResponse


class AdminLiveJobItem(BaseModel):
    job_id: str
    status: JobStatus
    verification_status: VerificationStatus
    prompt_preview: str
    model: str
    target_replicas: int
    successful_replicas: int
    inflight_replicas: int
    assigned_node_ids: list[str]
    failed_node_ids: list[str]
    verification_confidence: float
    updated_at: datetime


class AdminLiveJobsResponse(BaseModel):
    items: list[AdminLiveJobItem]
