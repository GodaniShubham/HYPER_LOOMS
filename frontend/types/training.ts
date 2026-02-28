export type ArtifactFramework = "pytorch" | "tensorflow" | "onnx" | "custom";
export type DatasetFormat = "parquet" | "jsonl" | "webdataset" | "csv" | "custom";
export type TrainingMode = "train" | "finetune" | "inference" | "evaluation";
export type BudgetProfile = "starter" | "scale" | "peak";
export type TrainingStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type ModelArtifact = {
  artifact_id: string;
  name: string;
  version: string;
  source_uri: string;
  framework: ArtifactFramework;
  precision: string;
  parameter_count_b: number;
  size_gb: number;
  metadata: Record<string, string | number | boolean>;
  created_at: string;
};

export type DatasetArtifact = {
  dataset_id: string;
  name: string;
  version: string;
  source_uri: string;
  format: DatasetFormat;
  train_samples: number;
  val_samples: number;
  test_samples: number;
  size_gb: number;
  schema: Record<string, string>;
  created_at: string;
};

export type NodeAllocationHint = {
  node_id: string;
  score: number;
  region: string;
  vram_total_gb: number;
  free_vram_gb: number;
};

export type ComputeEstimateRequest = {
  artifact_id: string;
  dataset_id: string;
  mode: TrainingMode;
  provider: string;
  replicas: number;
  target_epochs: number;
  batch_size: number;
  learning_rate: number;
  max_tokens: number;
  preferred_region?: string | null;
  budget_profile: BudgetProfile;
};

export type ComputeEstimateResponse = {
  required_vram_gb: number;
  required_ram_gb: number;
  estimated_duration_hours: number;
  estimated_cost_credits: number;
  recommended_replicas: number;
  node_candidates: NodeAllocationHint[];
  warnings: string[];
};

export type TrainingRun = {
  run_id: string;
  owner_id: string;
  objective: string;
  artifact_id: string;
  dataset_id: string;
  mode: TrainingMode;
  status: TrainingStatus;
  provider: string;
  preferred_region?: string | null;
  budget_profile: BudgetProfile;
  replicas: number;
  target_epochs: number;
  current_epoch: number;
  batch_size: number;
  learning_rate: number;
  max_tokens: number;
  estimated_vram_gb: number;
  estimated_ram_gb: number;
  estimated_duration_hours: number;
  estimated_cost_credits: number;
  assigned_node_ids: string[];
  train_loss?: number | null;
  val_loss?: number | null;
  eval_score?: number | null;
  best_checkpoint_uri?: string | null;
  progress_pct: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
  error?: string | null;
};

export type TrainingCheckpoint = {
  checkpoint_id: string;
  run_id: string;
  epoch: number;
  step: number;
  train_loss?: number | null;
  val_loss?: number | null;
  eval_score?: number | null;
  checkpoint_uri: string;
  created_at: string;
};

export type ModelArtifactCreateInput = {
  name: string;
  version: string;
  source_uri: string;
  framework: ArtifactFramework;
  precision: string;
  parameter_count_b: number;
  size_gb: number;
  metadata: Record<string, string | number | boolean>;
};

export type DatasetArtifactCreateInput = {
  name: string;
  version: string;
  source_uri: string;
  format: DatasetFormat;
  train_samples: number;
  val_samples: number;
  test_samples: number;
  size_gb: number;
  schema: Record<string, string>;
};

export type TrainingRunCreateInput = {
  owner_id: string;
  objective: string;
  artifact_id: string;
  dataset_id: string;
  mode: TrainingMode;
  provider: string;
  preferred_region?: string | null;
  budget_profile: BudgetProfile;
  replicas: number;
  target_epochs: number;
  batch_size: number;
  learning_rate: number;
  max_tokens: number;
};
