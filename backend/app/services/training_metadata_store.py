from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.models.training import (
    ArtifactFramework,
    BudgetProfile,
    DatasetArtifact,
    DatasetCreateRequest,
    DatasetFormat,
    ModelArtifact,
    ModelArtifactCreateRequest,
    TrainingCheckpoint,
    TrainingCheckpointCreateRequest,
    TrainingMode,
    TrainingRun,
    TrainingStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ModelArtifactORM(Base):
    __tablename__ = "model_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    precision: Mapped[str] = mapped_column(String(24), nullable=False, default="bf16")
    parameter_count_b: Mapped[float] = mapped_column(Float, nullable=False)
    size_gb: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DatasetArtifactORM(Base):
    __tablename__ = "dataset_artifacts"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    train_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    val_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_gb: Mapped[float] = mapped_column(Float, nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TrainingRunORM(Base):
    __tablename__ = "training_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artifact_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="fabric")
    preferred_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_profile: Mapped[str] = mapped_column(String(24), nullable=False, default=BudgetProfile.scale.value)
    replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    target_epochs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    learning_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0002)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    estimated_vram_gb: Mapped[float] = mapped_column(Float, nullable=False, default=4.0)
    estimated_ram_gb: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    estimated_duration_hours: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    estimated_cost_credits: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    assigned_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    train_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_checkpoint_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingCheckpointORM(Base):
    __tablename__ = "training_checkpoints"

    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    train_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    checkpoint_uri: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TrainingMetadataStore:
    def __init__(self, db_url: str) -> None:
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        self._engine = create_engine(db_url, future=True, connect_args=connect_args)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def init(self) -> None:
        self._ensure_sqlite_dir()
        Base.metadata.create_all(self._engine)

    def _ensure_sqlite_dir(self) -> None:
        url = str(self._engine.url)
        if not url.startswith("sqlite:///"):
            return
        db_path = url.replace("sqlite:///", "", 1)
        path_obj = Path(db_path)
        if path_obj.parent:
            path_obj.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_model_artifact(self, payload: ModelArtifactCreateRequest) -> ModelArtifact:
        artifact_id = f"model-{uuid4().hex[:12]}"
        with self._session() as session:
            row = ModelArtifactORM(
                artifact_id=artifact_id,
                name=payload.name.strip(),
                version=payload.version.strip(),
                source_uri=payload.source_uri.strip(),
                framework=payload.framework.value,
                precision=payload.precision.strip(),
                parameter_count_b=payload.parameter_count_b,
                size_gb=payload.size_gb,
                metadata_json=payload.metadata,
            )
            session.add(row)
            session.flush()
            return self._map_artifact(row)

    def list_model_artifacts(self) -> list[ModelArtifact]:
        with self._session() as session:
            rows = session.scalars(select(ModelArtifactORM).order_by(ModelArtifactORM.created_at.desc())).all()
            return [self._map_artifact(row) for row in rows]

    def get_model_artifact(self, artifact_id: str) -> ModelArtifact | None:
        with self._session() as session:
            row = session.get(ModelArtifactORM, artifact_id)
            return self._map_artifact(row) if row else None

    def create_dataset_artifact(self, payload: DatasetCreateRequest) -> DatasetArtifact:
        dataset_id = f"dataset-{uuid4().hex[:12]}"
        with self._session() as session:
            row = DatasetArtifactORM(
                dataset_id=dataset_id,
                name=payload.name.strip(),
                version=payload.version.strip(),
                source_uri=payload.source_uri.strip(),
                format=payload.format.value,
                train_samples=payload.train_samples,
                val_samples=payload.val_samples,
                test_samples=payload.test_samples,
                size_gb=payload.size_gb,
                schema_json=payload.schema_fields,
            )
            session.add(row)
            session.flush()
            return self._map_dataset(row)

    def list_dataset_artifacts(self) -> list[DatasetArtifact]:
        with self._session() as session:
            rows = session.scalars(select(DatasetArtifactORM).order_by(DatasetArtifactORM.created_at.desc())).all()
            return [self._map_dataset(row) for row in rows]

    def get_dataset_artifact(self, dataset_id: str) -> DatasetArtifact | None:
        with self._session() as session:
            row = session.get(DatasetArtifactORM, dataset_id)
            return self._map_dataset(row) if row else None

    def create_training_run(self, row_data: dict) -> TrainingRun:
        run_id = f"run-{uuid4().hex[:12]}"
        with self._session() as session:
            row = TrainingRunORM(
                run_id=run_id,
                owner_id=row_data["owner_id"],
                objective=row_data.get("objective", ""),
                artifact_id=row_data["artifact_id"],
                dataset_id=row_data["dataset_id"],
                mode=row_data["mode"],
                status=row_data["status"],
                provider=row_data["provider"],
                preferred_region=row_data.get("preferred_region"),
                budget_profile=row_data["budget_profile"],
                replicas=row_data["replicas"],
                target_epochs=row_data["target_epochs"],
                current_epoch=row_data.get("current_epoch", 0),
                batch_size=row_data["batch_size"],
                learning_rate=row_data["learning_rate"],
                max_tokens=row_data["max_tokens"],
                estimated_vram_gb=row_data["estimated_vram_gb"],
                estimated_ram_gb=row_data["estimated_ram_gb"],
                estimated_duration_hours=row_data["estimated_duration_hours"],
                estimated_cost_credits=row_data["estimated_cost_credits"],
                assigned_node_ids=row_data["assigned_node_ids"],
                train_loss=row_data.get("train_loss"),
                val_loss=row_data.get("val_loss"),
                eval_score=row_data.get("eval_score"),
                best_checkpoint_uri=row_data.get("best_checkpoint_uri"),
                started_at=row_data.get("started_at"),
                completed_at=row_data.get("completed_at"),
                updated_at=row_data.get("updated_at", utc_now()),
                error=row_data.get("error"),
            )
            session.add(row)
            session.flush()
            return self._map_training_run(row)

    def list_training_runs(self, status: TrainingStatus | None = None) -> list[TrainingRun]:
        with self._session() as session:
            stmt = select(TrainingRunORM).order_by(TrainingRunORM.created_at.desc())
            if status:
                stmt = stmt.where(TrainingRunORM.status == status.value)
            rows = session.scalars(stmt).all()
            return [self._map_training_run(row) for row in rows]

    def get_training_run(self, run_id: str) -> TrainingRun | None:
        with self._session() as session:
            row = session.get(TrainingRunORM, run_id)
            return self._map_training_run(row) if row else None

    def update_training_run(self, run_id: str, updates: dict) -> TrainingRun:
        with self._session() as session:
            row = session.get(TrainingRunORM, run_id)
            if not row:
                raise KeyError(f"Run '{run_id}' not found")
            for key, value in updates.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.add(row)
            session.flush()
            return self._map_training_run(row)

    def create_checkpoint(self, run_id: str, payload: TrainingCheckpointCreateRequest) -> TrainingCheckpoint:
        checkpoint_id = f"ckpt-{uuid4().hex[:12]}"
        with self._session() as session:
            run_row = session.get(TrainingRunORM, run_id)
            if not run_row:
                raise KeyError(f"Run '{run_id}' not found")
            row = TrainingCheckpointORM(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                epoch=payload.epoch,
                step=payload.step,
                train_loss=payload.train_loss,
                val_loss=payload.val_loss,
                eval_score=payload.eval_score,
                checkpoint_uri=payload.checkpoint_uri.strip(),
            )
            run_row.current_epoch = max(run_row.current_epoch, payload.epoch)
            run_row.train_loss = payload.train_loss if payload.train_loss is not None else run_row.train_loss
            run_row.val_loss = payload.val_loss if payload.val_loss is not None else run_row.val_loss
            run_row.eval_score = payload.eval_score if payload.eval_score is not None else run_row.eval_score
            run_row.best_checkpoint_uri = payload.checkpoint_uri.strip()
            run_row.updated_at = utc_now()
            session.add(row)
            session.add(run_row)
            session.flush()
            return self._map_checkpoint(row)

    def list_checkpoints(self, run_id: str) -> list[TrainingCheckpoint]:
        with self._session() as session:
            rows = session.scalars(
                select(TrainingCheckpointORM).where(TrainingCheckpointORM.run_id == run_id).order_by(TrainingCheckpointORM.epoch.desc())
            ).all()
            return [self._map_checkpoint(row) for row in rows]

    @staticmethod
    def _map_artifact(row: ModelArtifactORM) -> ModelArtifact:
        return ModelArtifact(
            artifact_id=row.artifact_id,
            name=row.name,
            version=row.version,
            source_uri=row.source_uri,
            framework=ArtifactFramework(row.framework),
            precision=row.precision,
            parameter_count_b=row.parameter_count_b,
            size_gb=row.size_gb,
            metadata=row.metadata_json or {},
            created_at=row.created_at,
        )

    @staticmethod
    def _map_dataset(row: DatasetArtifactORM) -> DatasetArtifact:
        return DatasetArtifact(
            dataset_id=row.dataset_id,
            name=row.name,
            version=row.version,
            source_uri=row.source_uri,
            format=DatasetFormat(row.format),
            train_samples=row.train_samples,
            val_samples=row.val_samples,
            test_samples=row.test_samples,
            size_gb=row.size_gb,
            schema_fields=row.schema_json or {},
            created_at=row.created_at,
        )

    @staticmethod
    def _map_training_run(row: TrainingRunORM) -> TrainingRun:
        progress_pct = 100.0 if row.target_epochs <= 0 else min(100.0, round((row.current_epoch / row.target_epochs) * 100, 2))
        return TrainingRun(
            run_id=row.run_id,
            owner_id=row.owner_id,
            objective=row.objective,
            artifact_id=row.artifact_id,
            dataset_id=row.dataset_id,
            mode=TrainingMode(row.mode),
            status=TrainingStatus(row.status),
            provider=row.provider,
            preferred_region=row.preferred_region,
            budget_profile=BudgetProfile(row.budget_profile),
            replicas=row.replicas,
            target_epochs=row.target_epochs,
            current_epoch=row.current_epoch,
            batch_size=row.batch_size,
            learning_rate=row.learning_rate,
            max_tokens=row.max_tokens,
            estimated_vram_gb=row.estimated_vram_gb,
            estimated_ram_gb=row.estimated_ram_gb,
            estimated_duration_hours=row.estimated_duration_hours,
            estimated_cost_credits=row.estimated_cost_credits,
            assigned_node_ids=row.assigned_node_ids or [],
            train_loss=row.train_loss,
            val_loss=row.val_loss,
            eval_score=row.eval_score,
            best_checkpoint_uri=row.best_checkpoint_uri,
            progress_pct=progress_pct,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            updated_at=row.updated_at,
            error=row.error,
        )

    @staticmethod
    def _map_checkpoint(row: TrainingCheckpointORM) -> TrainingCheckpoint:
        return TrainingCheckpoint(
            checkpoint_id=row.checkpoint_id,
            run_id=row.run_id,
            epoch=row.epoch,
            step=row.step,
            train_loss=row.train_loss,
            val_loss=row.val_loss,
            eval_score=row.eval_score,
            checkpoint_uri=row.checkpoint_uri,
            created_at=row.created_at,
        )
