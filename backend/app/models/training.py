from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactFramework(StrEnum):
    pytorch = "pytorch"
    tensorflow = "tensorflow"
    onnx = "onnx"
    custom = "custom"


class DatasetFormat(StrEnum):
    parquet = "parquet"
    jsonl = "jsonl"
    webdataset = "webdataset"
    csv = "csv"
    custom = "custom"


class TrainingMode(StrEnum):
    train = "train"
    finetune = "finetune"
    inference = "inference"
    evaluation = "evaluation"


class TrainingStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BudgetProfile(StrEnum):
    starter = "starter"
    scale = "scale"
    peak = "peak"


class ModelArtifactCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    version: str = Field(default="v1", min_length=1, max_length=80)
    source_uri: str = Field(min_length=8, max_length=2048)
    framework: ArtifactFramework = ArtifactFramework.pytorch
    precision: str = Field(default="bf16", min_length=2, max_length=24)
    parameter_count_b: float = Field(default=7.0, ge=0.1, le=5000)
    size_gb: float = Field(default=5.0, ge=0.1, le=100_000)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ModelArtifact(BaseModel):
    artifact_id: str
    name: str
    version: str
    source_uri: str
    framework: ArtifactFramework
    precision: str
    parameter_count_b: float
    size_gb: float
    metadata: dict[str, str | int | float | bool]
    created_at: datetime


class ModelArtifactListResponse(BaseModel):
    items: list[ModelArtifact]


class DatasetCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=2, max_length=200)
    version: str = Field(default="v1", min_length=1, max_length=80)
    source_uri: str = Field(min_length=8, max_length=2048)
    format: DatasetFormat = DatasetFormat.parquet
    train_samples: int = Field(default=50_000, ge=1)
    val_samples: int = Field(default=5_000, ge=0)
    test_samples: int = Field(default=5_000, ge=0)
    size_gb: float = Field(default=10.0, ge=0.01, le=500_000)
    schema_fields: dict[str, str] = Field(default_factory=dict, alias="schema")


class DatasetArtifact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_id: str
    name: str
    version: str
    source_uri: str
    format: DatasetFormat
    train_samples: int
    val_samples: int
    test_samples: int
    size_gb: float
    schema_fields: dict[str, str] = Field(default_factory=dict, alias="schema")
    created_at: datetime


class DatasetArtifactListResponse(BaseModel):
    items: list[DatasetArtifact]


class NodeAllocationHint(BaseModel):
    node_id: str
    score: float
    region: str
    vram_total_gb: float
    free_vram_gb: float


class ComputeEstimateRequest(BaseModel):
    artifact_id: str = Field(min_length=4, max_length=64)
    dataset_id: str = Field(min_length=4, max_length=64)
    mode: TrainingMode = TrainingMode.finetune
    provider: str = Field(default="fabric", min_length=3, max_length=16)
    replicas: int = Field(default=2, ge=1, le=32)
    target_epochs: int = Field(default=3, ge=1, le=200)
    batch_size: int = Field(default=8, ge=1, le=2048)
    learning_rate: float = Field(default=0.0002, gt=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=64, le=65_536)
    preferred_region: str | None = Field(default=None, max_length=64)
    budget_profile: BudgetProfile = BudgetProfile.scale

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value or "auto").strip().lower()


class ComputeEstimateResponse(BaseModel):
    required_vram_gb: float
    required_ram_gb: float
    estimated_duration_hours: float
    estimated_cost_credits: float
    recommended_replicas: int
    node_candidates: list[NodeAllocationHint]
    warnings: list[str]


class TrainingRunCreateRequest(BaseModel):
    owner_id: str = Field(default="anonymous", min_length=1, max_length=120)
    objective: str = Field(default="", max_length=4000)
    artifact_id: str = Field(min_length=4, max_length=64)
    dataset_id: str = Field(min_length=4, max_length=64)
    mode: TrainingMode = TrainingMode.finetune
    provider: str = Field(default="fabric", min_length=3, max_length=16)
    preferred_region: str | None = Field(default=None, max_length=64)
    budget_profile: BudgetProfile = BudgetProfile.scale
    replicas: int = Field(default=2, ge=1, le=32)
    target_epochs: int = Field(default=3, ge=1, le=200)
    batch_size: int = Field(default=8, ge=1, le=2048)
    learning_rate: float = Field(default=0.0002, gt=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=64, le=65_536)

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value or "auto").strip().lower()


class TrainingRun(BaseModel):
    run_id: str
    owner_id: str
    objective: str
    artifact_id: str
    dataset_id: str
    mode: TrainingMode
    status: TrainingStatus
    provider: str
    preferred_region: str | None
    budget_profile: BudgetProfile
    replicas: int
    target_epochs: int
    current_epoch: int
    batch_size: int
    learning_rate: float
    max_tokens: int
    estimated_vram_gb: float
    estimated_ram_gb: float
    estimated_duration_hours: float
    estimated_cost_credits: float
    assigned_node_ids: list[str]
    train_loss: float | None
    val_loss: float | None
    eval_score: float | None
    best_checkpoint_uri: str | None
    progress_pct: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    error: str | None


class TrainingRunListResponse(BaseModel):
    items: list[TrainingRun]


class TrainingCheckpointCreateRequest(BaseModel):
    epoch: int = Field(ge=1, le=2000)
    step: int = Field(default=0, ge=0)
    train_loss: float | None = Field(default=None, ge=0.0)
    val_loss: float | None = Field(default=None, ge=0.0)
    eval_score: float | None = Field(default=None, ge=0.0, le=1.0)
    checkpoint_uri: str = Field(min_length=8, max_length=2048)


class TrainingCheckpoint(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: f"ckpt-{uuid4().hex[:12]}")
    run_id: str
    epoch: int
    step: int
    train_loss: float | None
    val_loss: float | None
    eval_score: float | None
    checkpoint_uri: str
    created_at: datetime = Field(default_factory=utc_now)


class TrainingCheckpointListResponse(BaseModel):
    items: list[TrainingCheckpoint]
