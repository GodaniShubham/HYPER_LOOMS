from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_training_orchestrator
from app.models.training import (
    ComputeEstimateRequest,
    ComputeEstimateResponse,
    DatasetArtifact,
    DatasetArtifactListResponse,
    DatasetCreateRequest,
    ModelArtifact,
    ModelArtifactCreateRequest,
    ModelArtifactListResponse,
    TrainingCheckpoint,
    TrainingCheckpointCreateRequest,
    TrainingCheckpointListResponse,
    TrainingRun,
    TrainingRunCreateRequest,
    TrainingRunListResponse,
    TrainingStatus,
)
from app.services.training_orchestrator import TrainingOrchestrator

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/artifacts", response_model=ModelArtifact, status_code=status.HTTP_201_CREATED)
async def create_model_artifact(
    payload: ModelArtifactCreateRequest,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> ModelArtifact:
    return orchestrator.create_model_artifact(payload)


@router.get("/artifacts", response_model=ModelArtifactListResponse)
async def list_model_artifacts(
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> ModelArtifactListResponse:
    return ModelArtifactListResponse(items=orchestrator.list_model_artifacts())


@router.get("/artifacts/{artifact_id}", response_model=ModelArtifact)
async def get_model_artifact(
    artifact_id: str,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> ModelArtifact:
    artifact = orchestrator.get_model_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model artifact not found")
    return artifact


@router.post("/datasets", response_model=DatasetArtifact, status_code=status.HTTP_201_CREATED)
async def create_dataset_artifact(
    payload: DatasetCreateRequest,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> DatasetArtifact:
    return orchestrator.create_dataset_artifact(payload)


@router.get("/datasets", response_model=DatasetArtifactListResponse)
async def list_dataset_artifacts(
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> DatasetArtifactListResponse:
    return DatasetArtifactListResponse(items=orchestrator.list_dataset_artifacts())


@router.get("/datasets/{dataset_id}", response_model=DatasetArtifact)
async def get_dataset_artifact(
    dataset_id: str,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> DatasetArtifact:
    dataset = orchestrator.get_dataset_artifact(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset artifact not found")
    return dataset


@router.post("/compute/estimate", response_model=ComputeEstimateResponse)
async def estimate_compute(
    payload: ComputeEstimateRequest,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> ComputeEstimateResponse:
    try:
        return await orchestrator.estimate_compute(payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/runs", response_model=TrainingRun, status_code=status.HTTP_202_ACCEPTED)
async def create_training_run(
    payload: TrainingRunCreateRequest,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingRun:
    try:
        return await orchestrator.create_training_run(payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/runs", response_model=TrainingRunListResponse)
async def list_training_runs(
    status_filter: TrainingStatus | None = Query(default=None, alias="status"),
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingRunListResponse:
    return TrainingRunListResponse(items=orchestrator.list_training_runs(status=status_filter))


@router.get("/runs/{run_id}", response_model=TrainingRun)
async def get_training_run(
    run_id: str,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingRun:
    run = orchestrator.get_training_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found")
    return run


@router.post("/runs/{run_id}/checkpoints", response_model=TrainingCheckpoint, status_code=status.HTTP_201_CREATED)
async def append_training_checkpoint(
    run_id: str,
    payload: TrainingCheckpointCreateRequest,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingCheckpoint:
    try:
        return orchestrator.append_training_checkpoint(run_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runs/{run_id}/checkpoints", response_model=TrainingCheckpointListResponse)
async def list_training_checkpoints(
    run_id: str,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingCheckpointListResponse:
    return TrainingCheckpointListResponse(items=orchestrator.list_training_checkpoints(run_id))


@router.post("/runs/{run_id}/cancel", response_model=TrainingRun)
async def cancel_training_run(
    run_id: str,
    orchestrator: TrainingOrchestrator = Depends(get_training_orchestrator),
) -> TrainingRun:
    try:
        return orchestrator.cancel_training_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

