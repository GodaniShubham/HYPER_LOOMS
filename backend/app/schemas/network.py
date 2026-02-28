from pydantic import BaseModel

from app.models.job import JobStatus
from app.models.node import Node


class NetworkStats(BaseModel):
    active_nodes: int
    total_nodes: int
    total_vram_gb: float
    jobs_running: int
    avg_latency_ms: float


class NetworkSnapshot(BaseModel):
    stats: NetworkStats
    nodes: list[Node]
    running_jobs: int


class JobStatusCount(BaseModel):
    status: JobStatus
    count: int

