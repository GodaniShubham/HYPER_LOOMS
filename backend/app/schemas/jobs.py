from datetime import datetime

from pydantic import BaseModel, Field

from app.models.domain import JobStatus, NodeExecutionResult, VerificationSummary


class JobSubmitRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=8000)
    model: str = Field(default="llama3.1-70b")
    replicas: int = Field(default=2, ge=1, le=8)
    max_tokens: int = Field(default=512, ge=64, le=4096)


class JobResponse(BaseModel):
    id: str
    prompt: str
    status: JobStatus
    model: str
    replicas: int
    max_tokens: int
    assigned_nodes: list[str]
    node_results: list[NodeExecutionResult]
    verification: VerificationSummary | None
    final_output: str | None
    logs: list[dict]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    latency_ms: int | None
    error: str | None


class JobsListResponse(BaseModel):
    jobs: list[JobResponse]

