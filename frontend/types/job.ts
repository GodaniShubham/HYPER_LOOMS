export type JobStatus = "pending" | "running" | "verifying" | "completed" | "failed";
export type VerificationStatus = "pending" | "verified" | "mismatch" | "failed";

export type JobConfig = {
  model: string;
  provider: string;
  replicas: number;
  max_tokens: number;
  temperature: number;
  preferred_region?: string | null;
};

export type JobLogEntry = {
  timestamp: string;
  level: string;
  message: string;
  node_id?: string | null;
};

export type NodeExecutionResult = {
  node_id: string;
  output?: string | null;
  latency_ms: number;
  success: boolean;
  error?: string | null;
};

export type JobMetrics = {
  queue_ms: number;
  execution_ms: number;
  verification_ms: number;
  total_ms: number;
};

export type JobModel = {
  id: string;
  prompt: string;
  config: JobConfig;
  owner_id?: string;
  cost_estimate_credits?: number;
  status: JobStatus;
  verification_status: VerificationStatus;
  progress: number;
  assigned_node_ids: string[];
  results: NodeExecutionResult[];
  logs: JobLogEntry[];
  merged_output?: string | null;
  verification_confidence: number;
  created_at: string;
  updated_at: string;
  error?: string | null;
  metrics: JobMetrics;
};

export type JobCreateInput = {
  prompt: string;
  config: JobConfig;
  owner_id?: string;
};
