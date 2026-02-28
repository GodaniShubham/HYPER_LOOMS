"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Sparkles, Workflow } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { retryJob, getJob, listJobs, submitJob } from "@/services/api/jobs";
import { useJobDraftStore } from "@/store/job-draft-store";
import { useUiStore } from "@/store/ui-store";
import { JobLogEntry, JobModel } from "@/types/job";
import { LiveJobPanel } from "@/modules/jobs/components/live-job-panel";
import { PromptEditor, WorkloadProfile } from "@/modules/jobs/components/prompt-editor";
import { ResultViewer } from "@/modules/jobs/components/result-viewer";
import { TrainingControlCenter } from "@/modules/jobs/components/training-control-center";
import { useJobStream } from "@/modules/jobs/hooks/use-job-stream";
import { useRuntimeState } from "@/hooks/use-runtime-state";

function optimisticJob(prompt: string): JobModel {
  const now = new Date().toISOString();
  return {
    id: `optimistic-${Date.now()}`,
    prompt,
    config: {
      model: "fabric-workload-v1",
      provider: "fabric",
      replicas: 1,
      max_tokens: 512,
      temperature: 0.3,
      preferred_region: null,
    },
    status: "pending",
    verification_status: "pending",
    progress: 8,
    assigned_node_ids: [],
    results: [],
    logs: [{ timestamp: now, level: "info", message: "Submitting job to orchestrator" }],
    merged_output: null,
    verification_confidence: 0,
    created_at: now,
    updated_at: now,
    error: null,
    metrics: {
      queue_ms: 0,
      execution_ms: 0,
      verification_ms: 0,
      total_ms: 0,
    },
  };
}

const defaultProfile: WorkloadProfile = {
  mode: "train",
  modelArtifact: "",
  datasetProfile: "",
  objective: "",
  budgetProfile: "scale",
};

function composeWorkloadPrompt(prompt: string, profile: WorkloadProfile): string {
  const sections = [
    `workload_mode: ${profile.mode}`,
    `model_artifact: ${profile.modelArtifact || "not_provided"}`,
    `dataset_profile: ${profile.datasetProfile || "not_provided"}`,
    `budget_profile: ${profile.budgetProfile}`,
    `business_objective: ${profile.objective || "not_provided"}`,
    "",
    "instructions:",
    prompt.trim(),
  ];

  return sections.join("\n");
}

type WorkspaceMode = "training" | "inference";

export function JobConsole(): JSX.Element {
  const queryClient = useQueryClient();
  const runtime = useRuntimeState();
  const { prompt, config, setPrompt, setConfig } = useJobDraftStore();
  const { selectedJobId, setSelectedJobId } = useUiStore();

  const [workspace, setWorkspace] = useState<WorkspaceMode>("inference");
  const [activeJob, setActiveJob] = useState<JobModel | undefined>(undefined);
  const [logs, setLogs] = useState<JobLogEntry[]>([]);
  const [profile, setProfile] = useState<WorkloadProfile>(defaultProfile);

  const inferenceActive = workspace === "inference";

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => listJobs(),
    enabled: inferenceActive && runtime.isOnline,
    refetchInterval: inferenceActive && runtime.isInteractive ? 12000 : false,
  });

  const serverJobId = useMemo(() => {
    if (!activeJob?.id) {
      return selectedJobId;
    }
    return activeJob.id.startsWith("optimistic-") ? selectedJobId : activeJob.id;
  }, [activeJob?.id, selectedJobId]);

  const handleJobUpdate = useCallback((job: JobModel) => {
    setActiveJob(job);
    setLogs(job.logs);
  }, []);

  const handleJobLog = useCallback((entry: JobLogEntry) => {
    setLogs((existing) => [...existing, entry].slice(-300));
  }, []);

  const stream = useJobStream({
    jobId: inferenceActive ? serverJobId : undefined,
    onJobUpdate: handleJobUpdate,
    onLog: handleJobLog,
  });
  const jobStillActive =
    !activeJob || activeJob.status === "pending" || activeJob.status === "running" || activeJob.status === "verifying";

  const detailsQuery = useQuery({
    queryKey: ["job", serverJobId],
    queryFn: () => getJob(serverJobId!),
    enabled: inferenceActive && runtime.isOnline && Boolean(serverJobId),
    refetchInterval: inferenceActive && runtime.isInteractive && !stream.connected && jobStillActive ? 6000 : false,
  });

  useEffect(() => {
    if (detailsQuery.data) {
      setActiveJob(detailsQuery.data);
      setLogs(detailsQuery.data.logs);
    }
  }, [detailsQuery.data]);

  const submitMutation = useMutation({
    mutationFn: submitJob,
    onMutate: async (payload) => {
      const optimistic = optimisticJob(payload.prompt);
      optimistic.config = config;
      setActiveJob(optimistic);
      setLogs(optimistic.logs);
      toast.message("Dispatching workload...");
    },
    onSuccess: (job) => {
      setActiveJob(job);
      setLogs(job.logs);
      setSelectedJobId(job.id);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast.success(`Job ${job.id} queued`);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to submit job");
    },
  });

  const retryMutation = useMutation({
    mutationFn: retryJob,
    onSuccess: (job) => {
      setActiveJob(job);
      setSelectedJobId(job.id);
      setLogs(job.logs);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Retry submitted");
    },
    onError: (error: Error) => toast.error(error.message || "Retry failed"),
  });

  return (
    <div className="space-y-4">
      <Card className="surface-panel border-primary/35">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="section-kicker">Startup Command Center</p>
            <h1 className="text-2xl font-semibold text-foreground">Customer Pathway for Training and Validation</h1>
            <p className="text-sm text-muted-foreground">
              Confusion avoid karne ke liye flow do workspaces me split hai: primary `Startup Training` aur optional
              `Prompt Inference Validation`.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={workspace === "training" ? "primary" : "secondary"}
              onClick={() => setWorkspace("training")}
              className="min-w-[200px]"
            >
              <Workflow className="h-4 w-4" />
              Startup Training
            </Button>
            <Button
              variant={workspace === "inference" ? "primary" : "secondary"}
              onClick={() => setWorkspace("inference")}
              className="min-w-[200px]"
            >
              <Sparkles className="h-4 w-4" />
              Prompt Inference
            </Button>
          </div>
        </div>
      </Card>

      {workspace === "training" ? (
        <TrainingControlCenter />
      ) : (
        <>
          <Card className="border-primary/20 bg-background/35">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="section-kicker">Optional Workspace</p>
                <h2 className="text-lg font-semibold text-foreground">Prompt Validation and Node Response Check</h2>
              </div>
              <Badge tone="warning">Inference Lane</Badge>
            </div>
          </Card>

          <div className="grid gap-4 xl:grid-cols-[2fr,1fr]">
            <div className="space-y-4">
              <PromptEditor
                prompt={prompt}
                config={config}
                profile={profile}
                isSubmitting={submitMutation.isPending}
                onPromptChange={setPrompt}
                onConfigChange={setConfig}
                onProfileChange={(patch) => setProfile((state) => ({ ...state, ...patch }))}
                onRun={() =>
                  submitMutation.mutate({
                    prompt: composeWorkloadPrompt(prompt, profile),
                    config,
                  })
                }
              />

              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">Recent Inference Runs</h3>
                  <Badge tone="neutral">{jobsQuery.data?.length ?? 0} total</Badge>
                </div>
                {jobsQuery.isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : jobsQuery.isError ? (
                  <p className="text-sm text-danger">Failed to load jobs. Auto-retrying...</p>
                ) : jobsQuery.data && jobsQuery.data.length > 0 ? (
                  <div className="space-y-2">
                    {jobsQuery.data.slice(0, 8).map((job) => (
                      <button
                        key={job.id}
                        type="button"
                        onClick={() => {
                          setSelectedJobId(job.id);
                          setActiveJob(job);
                          setLogs(job.logs);
                        }}
                        className="flex w-full items-center justify-between rounded-xl border border-border bg-background/35 px-3 py-2 text-left text-xs transition hover:border-primary/40"
                      >
                        <span className="font-medium text-foreground">{job.id}</span>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No inference jobs yet.</p>
                )}
              </Card>
            </div>

            <LiveJobPanel
              job={activeJob}
              logs={logs}
              streamConnected={stream.connected}
              retrying={retryMutation.isPending}
              onRetry={activeJob ? () => retryMutation.mutate(activeJob.id) : undefined}
            />
          </div>

          {detailsQuery.isError ? (
            <Card className="text-sm text-danger">Failed to refresh active job. Using last known state.</Card>
          ) : null}

          <ResultViewer job={activeJob} />
        </>
      )}
    </div>
  );
}
