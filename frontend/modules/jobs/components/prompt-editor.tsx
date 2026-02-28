"use client";

import { Cpu, FolderInput, Sparkles, Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { JobConfig } from "@/types/job";

export type WorkloadMode = "train" | "finetune" | "inference" | "evaluation";

export type WorkloadProfile = {
  mode: WorkloadMode;
  modelArtifact: string;
  datasetProfile: string;
  objective: string;
  budgetProfile: "starter" | "scale" | "peak";
};

type PromptEditorProps = {
  prompt: string;
  config: JobConfig;
  profile: WorkloadProfile;
  isSubmitting: boolean;
  onPromptChange: (value: string) => void;
  onConfigChange: (patch: Partial<JobConfig>) => void;
  onProfileChange: (patch: Partial<WorkloadProfile>) => void;
  onRun: () => void;
};

const REGION_OPTIONS = [
  { label: "auto", value: "" },
  { label: "us-east-1", value: "us-east-1" },
  { label: "us-west-2", value: "us-west-2" },
  { label: "eu-west-1", value: "eu-west-1" },
  { label: "ap-south-1", value: "ap-south-1" },
];

function estimateTokens(prompt: string): number {
  const words = prompt.trim().length === 0 ? 0 : prompt.trim().split(/\s+/).length;
  return Math.ceil(words * 1.33);
}

export function PromptEditor({
  prompt,
  config,
  profile,
  isSubmitting,
  onPromptChange,
  onConfigChange,
  onProfileChange,
  onRun,
}: PromptEditorProps): JSX.Element {
  const tokenCount = estimateTokens(prompt);

  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="section-kicker">Workload Composer</p>
          <h2 className="text-xl font-semibold text-foreground">Prompt Inference Submission</h2>
          <p className="text-sm text-muted-foreground">
            Define prompt objective and runtime profile before dispatch.
          </p>
        </div>
        <span className="rounded-full border border-border bg-background/70 px-2.5 py-1 text-xs text-muted-foreground">
          ~{tokenCount} tokens
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-3 rounded-xl border border-border/80 bg-background/40 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <FolderInput className="h-4 w-4 text-primary" />
            Startup Intent
          </div>
          <label className="space-y-1 text-xs text-muted-foreground">
            Use Case Mode
            <Select value={profile.mode} onChange={(event) => onProfileChange({ mode: event.target.value as WorkloadMode })}>
              <option value="train">train</option>
              <option value="finetune">finetune</option>
              <option value="inference">inference</option>
              <option value="evaluation">evaluation</option>
            </Select>
          </label>
          <label className="space-y-1 text-xs text-muted-foreground">
            Model Artifact (HF/S3/Registry Path)
            <Input
              value={profile.modelArtifact}
              onChange={(event) => onProfileChange({ modelArtifact: event.target.value })}
              placeholder="hf://org/model-name"
            />
          </label>
          <label className="space-y-1 text-xs text-muted-foreground">
            Dataset Profile
            <Input
              value={profile.datasetProfile}
              onChange={(event) => onProfileChange({ datasetProfile: event.target.value })}
              placeholder="customer-support-v2, 250k samples"
            />
          </label>
        </div>

        <div className="space-y-3 rounded-xl border border-border/80 bg-background/40 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Target className="h-4 w-4 text-primary" />
            Business Guardrails
          </div>
          <label className="space-y-1 text-xs text-muted-foreground">
            Objective
            <Textarea
              value={profile.objective}
              onChange={(event) => onProfileChange({ objective: event.target.value })}
              placeholder="What outcome should this run optimize for?"
              className="min-h-[120px]"
            />
          </label>
          <label className="space-y-1 text-xs text-muted-foreground">
            Budget / SLA Profile
            <Select
              value={profile.budgetProfile}
              onChange={(event) => onProfileChange({ budgetProfile: event.target.value as WorkloadProfile["budgetProfile"] })}
            >
              <option value="starter">starter (low cost)</option>
              <option value="scale">scale (balanced)</option>
              <option value="peak">peak (high throughput)</option>
            </Select>
          </label>
        </div>
      </div>

      <Textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        placeholder="Detailed run instructions, acceptance criteria, expected output format..."
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1 text-xs text-muted-foreground">
          Replicas
          <Select value={String(config.replicas)} onChange={(event) => onConfigChange({ replicas: Number(event.target.value) })}>
            {[1, 2, 3, 4].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </label>

        <label className="space-y-1 text-xs text-muted-foreground">
          Max Tokens
          <Input
            type="number"
            value={String(config.max_tokens)}
            onChange={(event) => onConfigChange({ max_tokens: Number(event.target.value) })}
            min={64}
            max={8192}
            step={64}
          />
        </label>

        <label className="space-y-1 text-xs text-muted-foreground">
          Temperature
          <Input
            type="number"
            value={String(config.temperature)}
            onChange={(event) => onConfigChange({ temperature: Number(event.target.value) })}
            min={0}
            max={2}
            step={0.1}
          />
        </label>

        <label className="space-y-1 text-xs text-muted-foreground">
          Preferred Region
          <Select
            value={config.preferred_region ?? ""}
            onChange={(event) => onConfigChange({ preferred_region: event.target.value ? event.target.value : null })}
          >
            {REGION_OPTIONS.map((item) => (
              <option key={item.value || "auto"} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </label>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="inline-flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
          <Cpu className="h-3.5 w-3.5" />
          Fabric dispatch includes verification workflow
        </div>
        <Button onClick={onRun} disabled={isSubmitting || prompt.trim().length === 0} className="min-w-[160px]">
          <Sparkles className="h-4 w-4" />
          {isSubmitting ? "Dispatching..." : "Dispatch Workload"}
        </Button>
      </div>
    </Card>
  );
}
