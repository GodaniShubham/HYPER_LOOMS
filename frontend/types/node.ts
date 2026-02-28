export type NodeStatus = "healthy" | "busy" | "offline";

export type NodeModel = {
  id: string;
  gpu: string;
  vram_total_gb: number;
  vram_used_gb: number;
  status: NodeStatus;
  trust_score: number;
  jobs_running: number;
  latency_ms_avg: number;
  region: string;
  model_cache: string[];
  last_heartbeat: string;
};

export type NodeRegisterInput = {
  id?: string;
  gpu: string;
  vram_total_gb: number;
  region?: string;
  model_cache?: string[];
};
