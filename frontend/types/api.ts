import { JobStatus } from "@/types/job";
import { NodeModel } from "@/types/node";

export type NetworkStats = {
  active_nodes: number;
  total_nodes: number;
  total_vram_gb: number;
  jobs_running: number;
  avg_latency_ms: number;
};

export type NetworkSnapshot = {
  stats: NetworkStats;
  nodes: NodeModel[];
  running_jobs: number;
};

export type NodeJobDistributionItem = {
  node_id: string;
  jobs: number;
  status: "healthy" | "busy" | "offline";
  trust_score: number;
};

export type JobStatusCount = {
  status: JobStatus;
  count: number;
};

export type AdminLiveJobItem = {
  job_id: string;
  status: JobStatus;
  verification_status: "pending" | "verified" | "mismatch" | "failed";
  prompt_preview: string;
  model: string;
  target_replicas: number;
  successful_replicas: number;
  inflight_replicas: number;
  assigned_node_ids: string[];
  failed_node_ids: string[];
  verification_confidence: number;
  updated_at: string;
};

export type ApiListResponse<T> = {
  items: T[];
};
