from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from random import random

from app.models.job import JobConfig
from app.models.node import NodeStatus
from app.models.training import (
    ComputeEstimateRequest,
    ComputeEstimateResponse,
    DatasetArtifact,
    DatasetCreateRequest,
    ModelArtifact,
    ModelArtifactCreateRequest,
    NodeAllocationHint,
    TrainingCheckpoint,
    TrainingCheckpointCreateRequest,
    TrainingRun,
    TrainingRunCreateRequest,
    TrainingStatus,
)
from app.services.credit_ledger import CreditLedger
from app.services.scheduler import WeightedScheduler
from app.services.state_store import InMemoryStateStore
from app.services.training_metadata_store import TrainingMetadataStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingOrchestrator:
    def __init__(
        self,
        metadata_store: TrainingMetadataStore,
        scheduler: WeightedScheduler,
        state_store: InMemoryStateStore,
        credits: CreditLedger | None = None,
        credit_per_gpu_hour: float = 14.0,
    ) -> None:
        self._metadata = metadata_store
        self._scheduler = scheduler
        self._state = state_store
        self._credits = credits
        self._credit_per_gpu_hour = max(0.01, credit_per_gpu_hour)

    def create_model_artifact(self, payload: ModelArtifactCreateRequest) -> ModelArtifact:
        return self._metadata.create_model_artifact(payload)

    def list_model_artifacts(self) -> list[ModelArtifact]:
        return self._metadata.list_model_artifacts()

    def get_model_artifact(self, artifact_id: str) -> ModelArtifact | None:
        return self._metadata.get_model_artifact(artifact_id)

    def create_dataset_artifact(self, payload: DatasetCreateRequest) -> DatasetArtifact:
        return self._metadata.create_dataset_artifact(payload)

    def list_dataset_artifacts(self) -> list[DatasetArtifact]:
        return self._metadata.list_dataset_artifacts()

    def get_dataset_artifact(self, dataset_id: str) -> DatasetArtifact | None:
        return self._metadata.get_dataset_artifact(dataset_id)

    async def estimate_compute(self, payload: ComputeEstimateRequest) -> ComputeEstimateResponse:
        artifact = self._metadata.get_model_artifact(payload.artifact_id)
        if not artifact:
            raise KeyError(f"Model artifact '{payload.artifact_id}' not found")
        dataset = self._metadata.get_dataset_artifact(payload.dataset_id)
        if not dataset:
            raise KeyError(f"Dataset artifact '{payload.dataset_id}' not found")

        config = JobConfig(
            model=f"{artifact.name}-{artifact.parameter_count_b:.1f}b",
            provider=payload.provider,
            replicas=payload.replicas,
            max_tokens=payload.max_tokens,
            preferred_region=payload.preferred_region,
        )
        nodes = await self._state.list_nodes()
        ranked = self._scheduler.rank_nodes(nodes, config)
        active_nodes = [node for node in nodes if node.status != NodeStatus.offline]
        fallback_candidates = sorted(
            active_nodes,
            key=lambda node: (
                1 if node.status == NodeStatus.healthy else 0,
                node.trust_score,
                node.free_vram_gb,
                node.id,
            ),
            reverse=True,
        )
        effective_candidates = ranked if ranked else fallback_candidates
        required_vram = max(2.0, self._scheduler.estimate_required_vram_gb(config))
        required_ram = max(4.0, round(required_vram * 1.65, 2))
        recommended_replicas = max(1, min(payload.replicas, len(effective_candidates) if effective_candidates else 1))

        token_factor = max(0.5, min(8.0, payload.max_tokens / 1024))
        mode_factor = {
            "train": 1.5,
            "finetune": 1.0,
            "inference": 0.35,
            "evaluation": 0.45,
        }[payload.mode.value]
        budget_factor = {
            "starter": 1.35,
            "scale": 1.0,
            "peak": 0.7,
        }[payload.budget_profile.value]

        samples = max(1, dataset.train_samples)
        steps_per_epoch = ceil(samples / max(1, payload.batch_size * recommended_replicas))
        step_seconds = max(0.04, (required_vram / 16) * mode_factor * token_factor * budget_factor)
        estimated_duration_hours = round((steps_per_epoch * payload.target_epochs * step_seconds) / 3600, 3)
        estimated_cost_credits = round(estimated_duration_hours * recommended_replicas * self._credit_per_gpu_hour, 2)

        warnings: list[str] = []
        if not ranked and fallback_candidates:
            warnings.append(
                "Using single-node MVP fallback for planning because strict VRAM match was not found. "
                "Run will execute sequentially on available node(s)."
            )
        elif not ranked:
            warnings.append("No healthy nodes currently match VRAM requirements. Run will queue until capacity appears.")
        if recommended_replicas < payload.replicas:
            warnings.append(
                f"Requested replicas reduced from {payload.replicas} to {recommended_replicas} due to current fabric capacity."
            )
        if dataset.size_gb > 500:
            warnings.append("Large dataset detected. Ensure shard streaming is configured on worker nodes.")

        candidates = [
            NodeAllocationHint(
                node_id=node.id,
                score=round(self._scheduler.score_node(node, config), 4),
                region=node.region,
                vram_total_gb=node.vram_total_gb,
                free_vram_gb=node.free_vram_gb,
            )
            for node in effective_candidates[:8]
        ]

        return ComputeEstimateResponse(
            required_vram_gb=round(required_vram, 2),
            required_ram_gb=round(required_ram, 2),
            estimated_duration_hours=estimated_duration_hours,
            estimated_cost_credits=estimated_cost_credits,
            recommended_replicas=recommended_replicas,
            node_candidates=candidates,
            warnings=warnings,
        )

    async def create_training_run(self, payload: TrainingRunCreateRequest) -> TrainingRun:
        estimate_payload = ComputeEstimateRequest(
            artifact_id=payload.artifact_id,
            dataset_id=payload.dataset_id,
            mode=payload.mode,
            provider=payload.provider,
            replicas=payload.replicas,
            target_epochs=payload.target_epochs,
            batch_size=payload.batch_size,
            learning_rate=payload.learning_rate,
            max_tokens=payload.max_tokens,
            preferred_region=payload.preferred_region,
            budget_profile=payload.budget_profile,
        )
        estimate = await self.estimate_compute(estimate_payload)
        assigned_nodes = [item.node_id for item in estimate.node_candidates[: estimate.recommended_replicas]]

        if self._credits and estimate.estimated_cost_credits > 0:
            await self._credits.charge_user_for_job(
                payload.owner_id,
                f"train-{payload.artifact_id}-{payload.dataset_id}",
                estimate.estimated_cost_credits,
            )

        return self._metadata.create_training_run(
            {
                "owner_id": payload.owner_id,
                "objective": payload.objective.strip(),
                "artifact_id": payload.artifact_id,
                "dataset_id": payload.dataset_id,
                "mode": payload.mode.value,
                "status": TrainingStatus.queued.value,
                "provider": payload.provider,
                "preferred_region": payload.preferred_region,
                "budget_profile": payload.budget_profile.value,
                "replicas": estimate.recommended_replicas,
                "target_epochs": payload.target_epochs,
                "current_epoch": 0,
                "batch_size": payload.batch_size,
                "learning_rate": payload.learning_rate,
                "max_tokens": payload.max_tokens,
                "estimated_vram_gb": estimate.required_vram_gb,
                "estimated_ram_gb": estimate.required_ram_gb,
                "estimated_duration_hours": estimate.estimated_duration_hours,
                "estimated_cost_credits": estimate.estimated_cost_credits,
                "assigned_node_ids": assigned_nodes,
                "started_at": None,
                "completed_at": None,
                "error": None,
            }
        )

    def list_training_runs(self, status: TrainingStatus | None = None) -> list[TrainingRun]:
        return self._metadata.list_training_runs(status=status)

    def get_training_run(self, run_id: str) -> TrainingRun | None:
        return self._metadata.get_training_run(run_id)

    def list_training_checkpoints(self, run_id: str) -> list[TrainingCheckpoint]:
        return self._metadata.list_checkpoints(run_id)

    def append_training_checkpoint(self, run_id: str, payload: TrainingCheckpointCreateRequest) -> TrainingCheckpoint:
        checkpoint = self._metadata.create_checkpoint(run_id, payload)
        run = self._metadata.get_training_run(run_id)
        if not run:
            raise KeyError(f"Run '{run_id}' not found")
        if run.current_epoch >= run.target_epochs and run.status not in {TrainingStatus.completed, TrainingStatus.cancelled}:
            self._metadata.update_training_run(
                run_id,
                {
                    "status": TrainingStatus.completed.value,
                    "completed_at": utc_now(),
                    "best_checkpoint_uri": checkpoint.checkpoint_uri,
                },
            )
        return checkpoint

    def cancel_training_run(self, run_id: str) -> TrainingRun:
        run = self._metadata.get_training_run(run_id)
        if not run:
            raise KeyError(f"Run '{run_id}' not found")
        if run.status in {TrainingStatus.completed, TrainingStatus.failed, TrainingStatus.cancelled}:
            return run
        return self._metadata.update_training_run(
            run_id,
            {
                "status": TrainingStatus.cancelled.value,
                "completed_at": utc_now(),
                "error": "Cancelled by operator",
            },
        )

    def tick_training_runs(self) -> list[TrainingRun]:
        runs = self._metadata.list_training_runs()
        updated: list[TrainingRun] = []
        for run in runs:
            if run.status in {TrainingStatus.completed, TrainingStatus.failed, TrainingStatus.cancelled}:
                continue
            if run.status == TrainingStatus.queued:
                updated.append(
                    self._metadata.update_training_run(
                        run.run_id,
                        {
                            "status": TrainingStatus.running.value,
                            "started_at": utc_now(),
                            "error": None,
                        },
                    )
                )
                continue

            next_epoch = min(run.target_epochs, run.current_epoch + 1)
            next_train_loss = max(0.01, round((run.train_loss or 2.2) * (0.78 + random() * 0.08), 4))
            next_val_loss = max(0.01, round((run.val_loss or 2.35) * (0.80 + random() * 0.09), 4))
            next_eval = min(0.99, round((run.eval_score or 0.42) + 0.03 + random() * 0.04, 4))
            checkpoint_uri = f"{run.artifact_id}/runs/{run.run_id}/epoch-{next_epoch:03d}.ckpt"

            checkpoint = self._metadata.create_checkpoint(
                run.run_id,
                TrainingCheckpointCreateRequest(
                    epoch=next_epoch,
                    step=max(1, next_epoch * 120),
                    train_loss=next_train_loss,
                    val_loss=next_val_loss,
                    eval_score=next_eval,
                    checkpoint_uri=checkpoint_uri,
                ),
            )

            status = TrainingStatus.completed.value if next_epoch >= run.target_epochs else TrainingStatus.running.value
            updates = {
                "status": status,
                "current_epoch": next_epoch,
                "train_loss": checkpoint.train_loss,
                "val_loss": checkpoint.val_loss,
                "eval_score": checkpoint.eval_score,
                "best_checkpoint_uri": checkpoint.checkpoint_uri,
                "completed_at": utc_now() if status == TrainingStatus.completed.value else None,
            }
            updated.append(self._metadata.update_training_run(run.run_id, updates))

        return updated
