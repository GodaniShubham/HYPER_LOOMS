"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, HardDriveDownload, Layers3, PlayCircle, Radar, Rocket } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelTrainingRun,
  createDatasetArtifact,
  createModelArtifact,
  createTrainingRun,
  estimateCompute,
  listDatasetArtifacts,
  listModelArtifacts,
  listTrainingCheckpoints,
  listTrainingRuns,
} from "@/services/api/training";
import { ComputeEstimateResponse, DatasetArtifactCreateInput, ModelArtifactCreateInput, TrainingRun } from "@/types/training";
import { useRuntimeState } from "@/hooks/use-runtime-state";

const defaultModelForm: ModelArtifactCreateInput = {
  name: "startup-foundation-model",
  version: "v1",
  source_uri: "s3://bucket/models/startup-foundation-model/v1",
  framework: "pytorch",
  precision: "bf16",
  parameter_count_b: 7,
  size_gb: 14,
  metadata: {},
};

const defaultDatasetForm: DatasetArtifactCreateInput = {
  name: "startup-domain-dataset",
  version: "v1",
  source_uri: "s3://bucket/datasets/startup-domain/v1",
  format: "parquet",
  train_samples: 120000,
  val_samples: 12000,
  test_samples: 12000,
  size_gb: 80,
  schema: { input: "text", target: "text" },
};

type RunDraft = {
  owner_id: string;
  objective: string;
  artifact_id: string;
  dataset_id: string;
  mode: "train" | "finetune" | "inference" | "evaluation";
  provider: "fabric";
  preferred_region: string;
  budget_profile: "starter" | "scale" | "peak";
  replicas: number;
  target_epochs: number;
  batch_size: number;
  learning_rate: number;
  max_tokens: number;
};

const defaultRunDraft: RunDraft = {
  owner_id: "startup-user",
  objective: "Fine-tune model for domain assistant quality and lower hallucinations.",
  artifact_id: "",
  dataset_id: "",
  mode: "finetune",
  provider: "fabric",
  preferred_region: "",
  budget_profile: "scale",
  replicas: 2,
  target_epochs: 3,
  batch_size: 8,
  learning_rate: 0.0002,
  max_tokens: 1024,
};

type StepId = "model" | "dataset" | "plan" | "monitor";

type StepDescriptor = {
  id: StepId;
  title: string;
  description: string;
  guidance: string;
  icon: typeof Layers3;
};

const pipelineSteps: StepDescriptor[] = [
  {
    id: "model",
    title: "Model Onboarding",
    description: "Base model artifact register karo.",
    guidance: "Give: model URI, framework, precision, size.",
    icon: Layers3,
  },
  {
    id: "dataset",
    title: "Dataset Onboarding",
    description: "Training dataset metadata register karo.",
    guidance: "Give: dataset URI, format, sample counts, size.",
    icon: Database,
  },
  {
    id: "plan",
    title: "Compute Plan + Launch",
    description: "Cost/time estimate ke baad run launch karo.",
    guidance: "Give: objective, replicas, epochs, budget profile.",
    icon: Rocket,
  },
  {
    id: "monitor",
    title: "Run Monitoring",
    description: "Progress, checkpoints, cancel/resume decisions.",
    guidance: "Track: run health, loss metrics, checkpoint state.",
    icon: Radar,
  },
];

function statusTone(status: TrainingRun["status"]): "neutral" | "warning" | "success" | "danger" {
  if (status === "completed") {
    return "success";
  }
  if (status === "running" || status === "queued") {
    return "warning";
  }
  if (status === "failed" || status === "cancelled") {
    return "danger";
  }
  return "neutral";
}

type StepState = "active" | "done" | "locked";

function resolveStepState(step: StepId, hasModel: boolean, hasDataset: boolean, hasPlan: boolean, hasRun: boolean): StepState {
  if (step === "model") {
    return hasModel ? "done" : "active";
  }
  if (step === "dataset") {
    if (!hasModel) {
      return "locked";
    }
    return hasDataset ? "done" : "active";
  }
  if (step === "plan") {
    if (!hasModel || !hasDataset) {
      return "locked";
    }
    return hasPlan ? "done" : "active";
  }
  if (!hasRun) {
    return "locked";
  }
  return "active";
}

export function TrainingControlCenter(): JSX.Element {
  const queryClient = useQueryClient();
  const runtime = useRuntimeState();

  const [activeStep, setActiveStep] = useState<StepId>("model");
  const [modelForm, setModelForm] = useState<ModelArtifactCreateInput>(defaultModelForm);
  const [datasetForm, setDatasetForm] = useState<DatasetArtifactCreateInput>(defaultDatasetForm);
  const [runDraft, setRunDraft] = useState<RunDraft>(defaultRunDraft);
  const [estimate, setEstimate] = useState<ComputeEstimateResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");

  const modelArtifactsQuery = useQuery({
    queryKey: ["training-model-artifacts"],
    queryFn: listModelArtifacts,
    enabled: runtime.isOnline,
    retry: 0,
    refetchInterval: (query) => (runtime.isInteractive && !query.state.error ? 45000 : false),
  });
  const datasetsQuery = useQuery({
    queryKey: ["training-datasets"],
    queryFn: listDatasetArtifacts,
    enabled: runtime.isOnline,
    retry: 0,
    refetchInterval: (query) => (runtime.isInteractive && !query.state.error ? 45000 : false),
  });
  const runsQuery = useQuery({
    queryKey: ["training-runs"],
    queryFn: () => listTrainingRuns(),
    enabled: runtime.isOnline,
    retry: 0,
    refetchInterval: (query) => (runtime.isInteractive && !query.state.error ? 10000 : false),
  });

  const sortedRuns = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const activeRunId = selectedRunId || sortedRuns[0]?.run_id || "";

  const checkpointsQuery = useQuery({
    queryKey: ["training-checkpoints", activeRunId],
    queryFn: () => listTrainingCheckpoints(activeRunId),
    enabled: runtime.isOnline && activeStep === "monitor" && Boolean(activeRunId),
    retry: 0,
    refetchInterval: (query) => (runtime.isInteractive && activeStep === "monitor" && !query.state.error ? 9000 : false),
  });

  const createModelMutation = useMutation({
    mutationFn: createModelArtifact,
    onSuccess: (artifact) => {
      toast.success(`Model artifact registered: ${artifact.artifact_id}`);
      setRunDraft((state) => ({ ...state, artifact_id: artifact.artifact_id }));
      setActiveStep("dataset");
      queryClient.invalidateQueries({ queryKey: ["training-model-artifacts"] });
    },
    onError: (error: Error) => toast.error(error.message || "Failed to register model artifact"),
  });

  const createDatasetMutation = useMutation({
    mutationFn: createDatasetArtifact,
    onSuccess: (dataset) => {
      toast.success(`Dataset registered: ${dataset.dataset_id}`);
      setRunDraft((state) => ({ ...state, dataset_id: dataset.dataset_id }));
      setActiveStep("plan");
      queryClient.invalidateQueries({ queryKey: ["training-datasets"] });
    },
    onError: (error: Error) => toast.error(error.message || "Failed to register dataset"),
  });

  const estimateMutation = useMutation({
    mutationFn: estimateCompute,
    onSuccess: (nextEstimate) => {
      setEstimate(nextEstimate);
      toast.success("Compute plan estimated");
    },
    onError: (error: Error) => toast.error(error.message || "Compute estimate failed"),
  });

  const createRunMutation = useMutation({
    mutationFn: createTrainingRun,
    onSuccess: (run) => {
      toast.success(`Training run queued: ${run.run_id}`);
      setSelectedRunId(run.run_id);
      setActiveStep("monitor");
      queryClient.invalidateQueries({ queryKey: ["training-runs"] });
    },
    onError: (error: Error) => toast.error(error.message || "Failed to create training run"),
  });

  const cancelRunMutation = useMutation({
    mutationFn: cancelTrainingRun,
    onSuccess: (run) => {
      toast.message(`Run cancelled: ${run.run_id}`);
      queryClient.invalidateQueries({ queryKey: ["training-runs"] });
    },
    onError: (error: Error) => toast.error(error.message || "Unable to cancel run"),
  });

  useEffect(() => {
    if (!runDraft.artifact_id && modelArtifactsQuery.data?.length) {
      setRunDraft((state) => ({ ...state, artifact_id: modelArtifactsQuery.data?.[0].artifact_id ?? "" }));
    }
  }, [modelArtifactsQuery.data, runDraft.artifact_id]);

  useEffect(() => {
    if (!runDraft.dataset_id && datasetsQuery.data?.length) {
      setRunDraft((state) => ({ ...state, dataset_id: datasetsQuery.data?.[0].dataset_id ?? "" }));
    }
  }, [datasetsQuery.data, runDraft.dataset_id]);

  const modelCount = modelArtifactsQuery.data?.length ?? 0;
  const datasetCount = datasetsQuery.data?.length ?? 0;
  const runningCount = sortedRuns.filter((run) => run.status === "running").length;

  const hasModel = modelCount > 0;
  const hasDataset = datasetCount > 0;
  const hasPlan = Boolean(estimate);
  const hasRun = sortedRuns.length > 0;
  const canEstimate = Boolean(runDraft.artifact_id && runDraft.dataset_id);

  return (
    <Card className="surface-panel space-y-5 border-primary/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <p className="section-kicker">Customer Training Pathway</p>
          <h2 className="text-2xl font-semibold text-foreground">Model Onboarding to Production Run</h2>
          <p className="text-sm text-muted-foreground">
            Ek hi clear flow follow karein: pehle model register karo, phir dataset, uske baad compute estimate aur
            run launch karo. Monitoring panel me checkpoints aur run health verify karo.
          </p>
        </div>
        <div className="grid min-w-[240px] grid-cols-3 gap-2 text-xs">
          <div className="metal-panel rounded-lg px-3 py-2">
            <p className="text-muted-foreground">Models</p>
            <p className="text-lg font-semibold text-foreground">{modelCount}</p>
          </div>
          <div className="metal-panel rounded-lg px-3 py-2">
            <p className="text-muted-foreground">Datasets</p>
            <p className="text-lg font-semibold text-foreground">{datasetCount}</p>
          </div>
          <div className="metal-panel rounded-lg px-3 py-2">
            <p className="text-muted-foreground">Live Runs</p>
            <p className="text-lg font-semibold text-foreground">{runningCount}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-4">
        {pipelineSteps.map((step, index) => {
          const state = resolveStepState(step.id, hasModel, hasDataset, hasPlan, hasRun);
          const locked = state === "locked";
          const selected = activeStep === step.id;
          const Icon = step.icon;

          return (
            <button
              key={step.id}
              type="button"
              onClick={() => {
                if (!locked) {
                  setActiveStep(step.id);
                }
              }}
              className={[
                "pathway-step p-4 text-left",
                selected ? "pathway-step-active" : "",
                state === "done" ? "pathway-step-done" : "",
                locked ? "pathway-step-locked cursor-not-allowed" : "",
              ].join(" ")}
            >
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-border/80 bg-background/70 text-xs text-foreground">
                    {index + 1}
                  </span>
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <Badge tone={locked ? "neutral" : state === "done" ? "success" : "warning"}>
                  {locked ? "Locked" : state === "done" ? "Done" : "Active"}
                </Badge>
              </div>
              <p className="text-sm font-semibold text-foreground">{step.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{step.description}</p>
              <p className="mt-2 text-xs text-primary/95">{step.guidance}</p>
            </button>
          );
        })}
      </div>

      {activeStep === "model" ? (
        <Card className="space-y-4 border-border/80 bg-background/35">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">Step 1: Model Artifact Register</h3>
              <p className="text-sm text-muted-foreground">
                Customer ko base model ka source path aur technical profile dena hai.
              </p>
            </div>
            <Badge tone="warning">Required</Badge>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-1 text-xs text-muted-foreground">
              Model Name
              <Input
                value={modelForm.name}
                onChange={(event) => setModelForm((state) => ({ ...state, name: event.target.value }))}
                placeholder="Model name"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Version
              <Input
                value={modelForm.version}
                onChange={(event) => setModelForm((state) => ({ ...state, version: event.target.value }))}
                placeholder="Version"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Framework
              <Select
                value={modelForm.framework}
                onChange={(event) =>
                  setModelForm((state) => ({ ...state, framework: event.target.value as ModelArtifactCreateInput["framework"] }))
                }
              >
                <option value="pytorch">pytorch</option>
                <option value="tensorflow">tensorflow</option>
                <option value="onnx">onnx</option>
                <option value="custom">custom</option>
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Precision
              <Input
                value={modelForm.precision}
                onChange={(event) => setModelForm((state) => ({ ...state, precision: event.target.value }))}
                placeholder="bf16"
              />
            </label>
          </div>

          <label className="space-y-1 text-xs text-muted-foreground">
            Artifact URI
            <Input
              value={modelForm.source_uri}
              onChange={(event) => setModelForm((state) => ({ ...state, source_uri: event.target.value }))}
              placeholder="s3://... or hf://..."
            />
          </label>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-xs text-muted-foreground">
              Parameter Count (Billions)
              <Input
                type="number"
                value={String(modelForm.parameter_count_b)}
                onChange={(event) => setModelForm((state) => ({ ...state, parameter_count_b: Number(event.target.value) }))}
                placeholder="7"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Size (GB)
              <Input
                type="number"
                value={String(modelForm.size_gb)}
                onChange={(event) => setModelForm((state) => ({ ...state, size_gb: Number(event.target.value) }))}
                placeholder="14"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              Registered models: <span className="font-semibold text-foreground">{modelCount}</span>
            </div>
            <Button onClick={() => createModelMutation.mutate(modelForm)} disabled={createModelMutation.isPending}>
              <HardDriveDownload className="h-4 w-4" />
              {createModelMutation.isPending ? "Registering..." : "Register Model Artifact"}
            </Button>
          </div>
        </Card>
      ) : null}

      {activeStep === "dataset" ? (
        <Card className="space-y-4 border-border/80 bg-background/35">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">Step 2: Dataset Register</h3>
              <p className="text-sm text-muted-foreground">
                Dataset source aur volume details dene ke baad training-ready profile create hota hai.
              </p>
            </div>
            <Badge tone="warning">Required</Badge>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-1 text-xs text-muted-foreground">
              Dataset Name
              <Input
                value={datasetForm.name}
                onChange={(event) => setDatasetForm((state) => ({ ...state, name: event.target.value }))}
                placeholder="Dataset name"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Version
              <Input
                value={datasetForm.version}
                onChange={(event) => setDatasetForm((state) => ({ ...state, version: event.target.value }))}
                placeholder="Version"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Format
              <Select
                value={datasetForm.format}
                onChange={(event) =>
                  setDatasetForm((state) => ({ ...state, format: event.target.value as DatasetArtifactCreateInput["format"] }))
                }
              >
                <option value="parquet">parquet</option>
                <option value="jsonl">jsonl</option>
                <option value="webdataset">webdataset</option>
                <option value="csv">csv</option>
                <option value="custom">custom</option>
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Size (GB)
              <Input
                type="number"
                value={String(datasetForm.size_gb)}
                onChange={(event) => setDatasetForm((state) => ({ ...state, size_gb: Number(event.target.value) }))}
                placeholder="80"
              />
            </label>
          </div>

          <label className="space-y-1 text-xs text-muted-foreground">
            Dataset URI
            <Input
              value={datasetForm.source_uri}
              onChange={(event) => setDatasetForm((state) => ({ ...state, source_uri: event.target.value }))}
              placeholder="s3://bucket/datasets/domain/v1"
            />
          </label>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="space-y-1 text-xs text-muted-foreground">
              Train Samples
              <Input
                type="number"
                value={String(datasetForm.train_samples)}
                onChange={(event) => setDatasetForm((state) => ({ ...state, train_samples: Number(event.target.value) }))}
                placeholder="120000"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Validation Samples
              <Input
                type="number"
                value={String(datasetForm.val_samples)}
                onChange={(event) => setDatasetForm((state) => ({ ...state, val_samples: Number(event.target.value) }))}
                placeholder="12000"
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Test Samples
              <Input
                type="number"
                value={String(datasetForm.test_samples)}
                onChange={(event) => setDatasetForm((state) => ({ ...state, test_samples: Number(event.target.value) }))}
                placeholder="12000"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              Registered datasets: <span className="font-semibold text-foreground">{datasetCount}</span>
            </div>
            <Button variant="secondary" onClick={() => createDatasetMutation.mutate(datasetForm)} disabled={createDatasetMutation.isPending}>
              <Database className="h-4 w-4" />
              {createDatasetMutation.isPending ? "Registering..." : "Register Dataset"}
            </Button>
          </div>
        </Card>
      ) : null}

      {activeStep === "plan" ? (
        <Card className="space-y-4 border-border/80 bg-background/35">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">Step 3: Compute Plan and Launch</h3>
              <p className="text-sm text-muted-foreground">
                Yahan user objective define karta hai, estimate run karta hai, phir training launch karta hai.
              </p>
            </div>
            <Badge tone={canEstimate ? "success" : "warning"}>{canEstimate ? "Ready" : "Needs model + dataset"}</Badge>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-xs text-muted-foreground">
              Model Artifact
              <Select
                value={runDraft.artifact_id}
                onChange={(event) => setRunDraft((state) => ({ ...state, artifact_id: event.target.value }))}
              >
                <option value="">Select model artifact</option>
                {(modelArtifactsQuery.data ?? []).map((artifact) => (
                  <option key={artifact.artifact_id} value={artifact.artifact_id}>
                    {artifact.name} ({artifact.version})
                  </option>
                ))}
              </Select>
            </label>

            <label className="space-y-1 text-xs text-muted-foreground">
              Dataset
              <Select
                value={runDraft.dataset_id}
                onChange={(event) => setRunDraft((state) => ({ ...state, dataset_id: event.target.value }))}
              >
                <option value="">Select dataset</option>
                {(datasetsQuery.data ?? []).map((dataset) => (
                  <option key={dataset.dataset_id} value={dataset.dataset_id}>
                    {dataset.name} ({dataset.version})
                  </option>
                ))}
              </Select>
            </label>
          </div>

          <label className="space-y-1 text-xs text-muted-foreground">
            Training Objective
            <Textarea
              value={runDraft.objective}
              onChange={(event) => setRunDraft((state) => ({ ...state, objective: event.target.value }))}
              className="min-h-[96px]"
              placeholder="Model ko kis outcome par optimize karna hai..."
            />
          </label>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <label className="space-y-1 text-xs text-muted-foreground">
              Mode
              <Select
                value={runDraft.mode}
                onChange={(event) => setRunDraft((state) => ({ ...state, mode: event.target.value as RunDraft["mode"] }))}
              >
                <option value="train">train</option>
                <option value="finetune">finetune</option>
                <option value="inference">inference</option>
                <option value="evaluation">evaluation</option>
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Budget
              <Select
                value={runDraft.budget_profile}
                onChange={(event) =>
                  setRunDraft((state) => ({ ...state, budget_profile: event.target.value as RunDraft["budget_profile"] }))
                }
              >
                <option value="starter">starter</option>
                <option value="scale">scale</option>
                <option value="peak">peak</option>
              </Select>
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Replicas
              <Input
                type="number"
                value={String(runDraft.replicas)}
                onChange={(event) => setRunDraft((state) => ({ ...state, replicas: Number(event.target.value) }))}
                min={1}
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Epochs
              <Input
                type="number"
                value={String(runDraft.target_epochs)}
                onChange={(event) => setRunDraft((state) => ({ ...state, target_epochs: Number(event.target.value) }))}
                min={1}
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Batch Size
              <Input
                type="number"
                value={String(runDraft.batch_size)}
                onChange={(event) => setRunDraft((state) => ({ ...state, batch_size: Number(event.target.value) }))}
                min={1}
              />
            </label>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="space-y-1 text-xs text-muted-foreground">
              Learning Rate
              <Input
                type="number"
                value={String(runDraft.learning_rate)}
                onChange={(event) => setRunDraft((state) => ({ ...state, learning_rate: Number(event.target.value) }))}
                step={0.0001}
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Max Tokens
              <Input
                type="number"
                value={String(runDraft.max_tokens)}
                onChange={(event) => setRunDraft((state) => ({ ...state, max_tokens: Number(event.target.value) }))}
              />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Preferred Region
              <Input
                value={runDraft.preferred_region}
                onChange={(event) => setRunDraft((state) => ({ ...state, preferred_region: event.target.value }))}
                placeholder="us-east-1 (optional)"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() =>
                estimateMutation.mutate({
                  artifact_id: runDraft.artifact_id,
                  dataset_id: runDraft.dataset_id,
                  mode: runDraft.mode,
                  provider: runDraft.provider,
                  replicas: runDraft.replicas,
                  target_epochs: runDraft.target_epochs,
                  batch_size: runDraft.batch_size,
                  learning_rate: runDraft.learning_rate,
                  max_tokens: runDraft.max_tokens,
                  preferred_region: runDraft.preferred_region || null,
                  budget_profile: runDraft.budget_profile,
                })
              }
              disabled={!canEstimate || estimateMutation.isPending}
            >
              {estimateMutation.isPending ? "Estimating..." : "Estimate Compute Plan"}
            </Button>

            <Button
              onClick={() =>
                createRunMutation.mutate({
                  owner_id: runDraft.owner_id,
                  objective: runDraft.objective,
                  artifact_id: runDraft.artifact_id,
                  dataset_id: runDraft.dataset_id,
                  mode: runDraft.mode,
                  provider: runDraft.provider,
                  preferred_region: runDraft.preferred_region || null,
                  budget_profile: runDraft.budget_profile,
                  replicas: runDraft.replicas,
                  target_epochs: runDraft.target_epochs,
                  batch_size: runDraft.batch_size,
                  learning_rate: runDraft.learning_rate,
                  max_tokens: runDraft.max_tokens,
                })
              }
              disabled={!canEstimate || createRunMutation.isPending}
            >
              <PlayCircle className="h-4 w-4" />
              {createRunMutation.isPending ? "Launching..." : "Launch Training Run"}
            </Button>
          </div>

          {estimate ? (
            <Card className="space-y-2 border-primary/30 bg-background/45">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-foreground">Estimator Output</h4>
                <Badge tone="warning">{estimate.recommended_replicas} recommended replicas</Badge>
              </div>
              <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
                <p>Required VRAM: {estimate.required_vram_gb.toFixed(2)} GB</p>
                <p>Required RAM: {estimate.required_ram_gb.toFixed(2)} GB</p>
                <p>Duration: {estimate.estimated_duration_hours.toFixed(2)} hrs</p>
                <p>Estimated Credits: {estimate.estimated_cost_credits.toFixed(2)}</p>
                <p>Candidates: {estimate.node_candidates.length}</p>
              </div>
              {estimate.warnings.length ? (
                <div className="space-y-1">
                  {estimate.warnings.map((warning) => (
                    <p key={warning} className="text-xs text-warning">
                      {warning}
                    </p>
                  ))}
                </div>
              ) : null}
            </Card>
          ) : null}
        </Card>
      ) : null}

      {activeStep === "monitor" ? (
        <Card className="space-y-4 border-border/80 bg-background/35">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">Step 4: Run Monitoring and Checkpoints</h3>
              <p className="text-sm text-muted-foreground">
                Production run ka status yahin track karo aur checkpoint integrity verify karo.
              </p>
            </div>
            <Badge tone={hasRun ? "success" : "neutral"}>{hasRun ? `${sortedRuns.length} runs` : "No run yet"}</Badge>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.5fr,1fr]">
            <div className="space-y-3">
              {sortedRuns.length === 0 ? (
                <div className="rounded-xl border border-border/80 bg-background/40 p-4 text-sm text-muted-foreground">
                  No runs yet. Step 3 me compute estimate karke launch run karein.
                </div>
              ) : (
                sortedRuns.map((run) => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => setSelectedRunId(run.run_id)}
                    className="w-full rounded-xl border border-border/80 bg-background/50 p-3 text-left transition hover:border-primary/40"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground">{run.run_id}</p>
                      <Badge tone={statusTone(run.status)}>{run.status}</Badge>
                    </div>
                    <Progress value={run.progress_pct} />
                    <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                      <p>
                        Epoch {run.current_epoch}/{run.target_epochs}
                      </p>
                      <p>Replicas {run.replicas}</p>
                      <p>Train loss {run.train_loss?.toFixed(4) ?? "-"}</p>
                      <p>Eval score {run.eval_score?.toFixed(4) ?? "-"}</p>
                    </div>
                  </button>
                ))
              )}
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-foreground">Run Checkpoints</h4>
                {activeRunId ? (
                  <Button
                    variant="danger"
                    className="px-3 py-1 text-xs"
                    onClick={() => cancelRunMutation.mutate(activeRunId)}
                    disabled={cancelRunMutation.isPending}
                  >
                    Cancel Run
                  </Button>
                ) : null}
              </div>
              {!activeRunId ? (
                <p className="text-sm text-muted-foreground">Select a run to inspect checkpoints.</p>
              ) : checkpointsQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Loading checkpoints...</p>
              ) : checkpointsQuery.data?.length ? (
                <div className="space-y-2">
                  {checkpointsQuery.data.map((checkpoint) => (
                    <div key={checkpoint.checkpoint_id} className="rounded-xl border border-border/80 bg-background/50 p-3">
                      <p className="text-xs font-semibold text-foreground">
                        Epoch {checkpoint.epoch} | Step {checkpoint.step}
                      </p>
                      <p className="text-xs text-muted-foreground">{checkpoint.checkpoint_uri}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        loss {checkpoint.train_loss?.toFixed(4) ?? "-"} | val {checkpoint.val_loss?.toFixed(4) ?? "-"} |
                        score {checkpoint.eval_score?.toFixed(4) ?? "-"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No checkpoints yet.</p>
              )}
            </div>
          </div>
        </Card>
      ) : null}

      <div className="flex items-center gap-2 rounded-xl border border-success/35 bg-success/10 px-3 py-2 text-xs text-success">
        <CheckCircle2 className="h-4 w-4" />
        Customer pathway is now linear: register model -&gt; register dataset -&gt; estimate -&gt; launch -&gt; monitor.
      </div>
    </Card>
  );
}
