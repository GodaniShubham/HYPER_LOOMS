import { fetchJson } from "@/services/api/client";
import { ApiListResponse } from "@/types/api";
import { NodeModel } from "@/types/node";

export async function listNodes(): Promise<NodeModel[]> {
  const response = await fetchJson<ApiListResponse<NodeModel>>("/api/v1/nodes");
  return response.items;
}

