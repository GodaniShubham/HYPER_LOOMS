from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    verifying = "verifying"
    completed = "completed"
    failed = "failed"


class VerificationStatus(StrEnum):
    pending = "pending"
    verified = "verified"
    mismatch = "mismatch"
    failed = "failed"


class JobConfig(BaseModel):
    model: str = Field(default="llama-3.1-70b")
    replicas: int = Field(default=2, ge=1, le=8)
    max_tokens: int = Field(default=512, ge=32, le=8192)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    provider: str = Field(default="fabric")
    preferred_region: str | None = Field(default=None)


class JobCreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    config: JobConfig = Field(default_factory=JobConfig)
    owner_id: str = Field(default="anonymous", min_length=1, max_length=200)


class JobLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    level: str = "info"
    message: str
    node_id: str | None = None


class NodeExecutionResult(BaseModel):
    node_id: str
    output: str | None = None
    latency_ms: float = Field(default=0, ge=0)
    success: bool = True
    error: str | None = None


class JobMetrics(BaseModel):
    queue_ms: float = 0
    execution_ms: float = 0
    verification_ms: float = 0
    total_ms: float = 0


class JobResultSubmitRequest(BaseModel):
    job_id: str | None = None
    output: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = Field(default=None, ge=0)
    assignment_hash_key: str | None = Field(default=None, min_length=12, max_length=300)


class JobFailureSubmitRequest(BaseModel):
    job_id: str | None = None
    error: str = Field(min_length=1, max_length=5000)
    raw: dict[str, Any] = Field(default_factory=dict)
    assignment_hash_key: str | None = Field(default=None, min_length=12, max_length=300)


class Job(BaseModel):
    id: str = Field(default_factory=lambda: f"job-{uuid4().hex[:12]}")
    prompt: str
    config: JobConfig
    owner_id: str = Field(default="anonymous", min_length=1, max_length=200)
    cost_estimate_credits: float = Field(default=0, ge=0)
    status: JobStatus = JobStatus.pending
    verification_status: VerificationStatus = VerificationStatus.pending
    progress: float = Field(default=0, ge=0, le=100)
    assigned_node_ids: list[str] = Field(default_factory=list)
    scheduled_node_ids: list[str] = Field(default_factory=list)
    inflight_node_ids: list[str] = Field(default_factory=list)
    failed_node_ids: list[str] = Field(default_factory=list)
    results: list[NodeExecutionResult] = Field(default_factory=list)
    logs: list[JobLogEntry | dict[str, Any]] = Field(default_factory=list)
    merged_output: str | None = None
    verification_confidence: float = Field(default=0, ge=0, le=1)
    verification_details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: str | None = None
    metrics: JobMetrics = Field(default_factory=JobMetrics)


class NodeJobClaimResponse(BaseModel):
    job: Job
    assignment_hash_key: str = Field(min_length=12, max_length=300)
    assignment_expires_at: datetime


class JobListResponse(BaseModel):
    items: list[Job]
