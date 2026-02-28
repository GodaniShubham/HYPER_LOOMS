import { fetchJson } from "@/services/api/client";
import { ApiListResponse } from "@/types/api";
import { JobCreateInput, JobModel, JobStatus } from "@/types/job";

export async function submitJob(payload: JobCreateInput): Promise<JobModel> {
  return fetchJson<JobModel>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getJob(jobId: string): Promise<JobModel> {
  return fetchJson<JobModel>(`/api/v1/jobs/${jobId}`, {
    retries: 1,
    backoffMs: 250,
  });
}

export async function listJobs(status?: JobStatus): Promise<JobModel[]> {
  const suffix = status ? `?status=${status}` : "";
  const response = await fetchJson<ApiListResponse<JobModel>>(`/api/v1/jobs${suffix}`);
  return response.items;
}

export async function retryJob(jobId: string): Promise<JobModel> {
  return fetchJson<JobModel>(`/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

