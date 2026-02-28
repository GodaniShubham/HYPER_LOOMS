"use client";

import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { JobLogEntry, JobModel } from "@/types/job";

type LiveJobPanelProps = {
  job?: JobModel;
  logs: JobLogEntry[];
  streamConnected: boolean;
  retrying?: boolean;
  onRetry?: () => void;
};

function statusTone(status: JobModel["status"]): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "verifying") {
    return "warning";
  }
  return "neutral";
}

export function LiveJobPanel({
  job,
  logs,
  streamConnected,
  retrying = false,
  onRetry,
}: LiveJobPanelProps): JSX.Element {
  return (
    <Card className="flex h-full flex-col gap-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Execution Telemetry</h3>
          <Badge tone={streamConnected ? "success" : "warning"}>
            {streamConnected ? "WS Connected" : "Polling"}
          </Badge>
        </div>
        {job ? (
          <>
            <div className="flex items-center gap-2">
              <Badge tone={statusTone(job.status)}>{job.status}</Badge>
              <span className="text-xs text-muted-foreground">Job ID: {job.id}</span>
            </div>
            <Progress value={job.progress} />
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <p>Nodes: {job.assigned_node_ids.length || "-"}</p>
              <p>Latency: {Math.round(job.metrics.total_ms || 0)} ms</p>
              <p>Verification: {job.verification_status}</p>
              <p>Confidence: {(job.verification_confidence * 100).toFixed(0)}%</p>
            </div>
            {job.status === "failed" && onRetry ? (
              <Button variant="danger" className="w-full" onClick={onRetry} disabled={retrying}>
                <RefreshCw className="h-4 w-4" />
                {retrying ? "Retrying..." : "Retry Job"}
              </Button>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No active run. Compose startup workload intent and dispatch the first compute plan.
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-background/40">
        <div className="border-b border-border px-3 py-2 text-xs uppercase tracking-wide text-muted-foreground">
          Verification Stream
        </div>
        <div className="h-[320px] space-y-2 overflow-y-auto px-3 py-3 text-xs">
          {logs.length === 0 ? (
            <p className="text-muted-foreground">Logs appear here once node replicas claim this run.</p>
          ) : (
            logs.map((log, index) => (
              <div key={`${log.timestamp}-${index}`} className="rounded-md border border-border/70 bg-white/5 px-2 py-1">
                <p className="text-muted-foreground">
                  {new Date(log.timestamp).toLocaleTimeString()} {log.node_id ? `[${log.node_id}]` : ""}
                </p>
                <p className={log.level === "error" ? "text-danger" : "text-foreground"}>{log.message}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </Card>
  );
}
