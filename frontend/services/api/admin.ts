import { fetchJson } from "@/services/api/client";
import { AdminLiveJobItem, ApiListResponse, JobStatusCount, NodeJobDistributionItem } from "@/types/api";
import { NodeModel, NodeRegisterInput } from "@/types/node";

export async function getAdminNodes(): Promise<NodeModel[]> {
  const response = await fetchJson<ApiListResponse<NodeModel>>("/api/v1/admin/nodes", {
    admin: true,
    retries: 1,
  });
  return response.items;
}

export async function getJobsDistribution(): Promise<NodeJobDistributionItem[]> {
  const response = await fetchJson<{ items: NodeJobDistributionItem[] }>("/api/v1/admin/jobs/distribution", {
    admin: true,
    retries: 1,
  });
  return response.items;
}

export async function getJobStatusCounts(): Promise<JobStatusCount[]> {
  return fetchJson<JobStatusCount[]>("/api/v1/admin/jobs/status-counts", {
    admin: true,
    retries: 1,
  });
}

export async function getLiveJobs(): Promise<AdminLiveJobItem[]> {
  const response = await fetchJson<{ items: AdminLiveJobItem[] }>("/api/v1/admin/jobs/live", {
    admin: true,
    retries: 1,
  });
  return response.items;
}

export async function registerLocalAdminNode(input?: Partial<NodeRegisterInput>): Promise<NodeModel> {
  const payload: NodeRegisterInput = {
    id: (input?.id || `web-local-${Date.now().toString(36)}`).trim(),
    gpu: input?.gpu || "Hyperlooms Web Node",
    vram_total_gb: input?.vram_total_gb ?? 4,
    region: input?.region || "local",
    model_cache: input?.model_cache ?? ["llama3"],
  };

  const response = await fetchJson<{ node: NodeModel }>("/api/v1/admin/nodes/register-local", {
    method: "POST",
    admin: true,
    retries: 0,
    body: JSON.stringify(payload),
  });
  return response.node;
}

export async function getLocalRegisteredNode(): Promise<NodeModel | null> {
  const response = await fetch("/api/local-node", { cache: "no-store" });
  if (!response.ok) {
    return null;
  }
  const data = (await response.json()) as { node?: NodeModel | null };
  return data.node ?? null;
}
