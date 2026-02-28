import { fetchJson } from "@/services/api/client";
import {
  ComputeEstimateRequest,
  ComputeEstimateResponse,
  DatasetArtifact,
  DatasetArtifactCreateInput,
  ModelArtifact,
  ModelArtifactCreateInput,
  TrainingCheckpoint,
  TrainingRun,
  TrainingRunCreateInput,
  TrainingStatus,
} from "@/types/training";

type ListResponse<T> = {
  items: T[];
};

export async function createModelArtifact(payload: ModelArtifactCreateInput): Promise<ModelArtifact> {
  return fetchJson<ModelArtifact>("/api/v1/training/artifacts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listModelArtifacts(): Promise<ModelArtifact[]> {
  const response = await fetchJson<ListResponse<ModelArtifact>>("/api/v1/training/artifacts", {
    retries: 1,
  });
  return response.items;
}

export async function createDatasetArtifact(payload: DatasetArtifactCreateInput): Promise<DatasetArtifact> {
  return fetchJson<DatasetArtifact>("/api/v1/training/datasets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listDatasetArtifacts(): Promise<DatasetArtifact[]> {
  const response = await fetchJson<ListResponse<DatasetArtifact>>("/api/v1/training/datasets", {
    retries: 1,
  });
  return response.items;
}

export async function estimateCompute(payload: ComputeEstimateRequest): Promise<ComputeEstimateResponse> {
  return fetchJson<ComputeEstimateResponse>("/api/v1/training/compute/estimate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createTrainingRun(payload: TrainingRunCreateInput): Promise<TrainingRun> {
  return fetchJson<TrainingRun>("/api/v1/training/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listTrainingRuns(status?: TrainingStatus): Promise<TrainingRun[]> {
  const suffix = status ? `?status=${status}` : "";
  const response = await fetchJson<ListResponse<TrainingRun>>(`/api/v1/training/runs${suffix}`, {
    retries: 1,
  });
  return response.items;
}

export async function getTrainingRun(runId: string): Promise<TrainingRun> {
  return fetchJson<TrainingRun>(`/api/v1/training/runs/${runId}`, {
    retries: 1,
    backoffMs: 250,
  });
}

export async function listTrainingCheckpoints(runId: string): Promise<TrainingCheckpoint[]> {
  const response = await fetchJson<ListResponse<TrainingCheckpoint>>(`/api/v1/training/runs/${runId}/checkpoints`, {
    retries: 1,
  });
  return response.items;
}

export async function cancelTrainingRun(runId: string): Promise<TrainingRun> {
  return fetchJson<TrainingRun>(`/api/v1/training/runs/${runId}/cancel`, {
    method: "POST",
  });
}

