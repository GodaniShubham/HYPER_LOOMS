import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { JobModel } from "@/types/job";

type ResultViewerProps = {
  job?: JobModel;
};

export function ResultViewer({ job }: ResultViewerProps): JSX.Element {
  if (!job) {
    return (
      <Card className="text-sm text-muted-foreground">
        No result selected. Dispatch a workload and open a run to inspect merged outputs.
      </Card>
    );
  }

  const completed = job.status === "completed";

  return (
    <div className="space-y-4">
      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="section-kicker">Run Result</p>
            <h2 className="text-lg font-semibold text-foreground">Merged Output + Verification Metadata</h2>
            <p className="text-sm text-muted-foreground">
              Final consensus artifact ready for startup review, QA, or deployment handoff.
            </p>
          </div>
          <Badge tone={completed ? "success" : "warning"}>{job.verification_status}</Badge>
        </div>

        <div className="rounded-xl border border-border bg-background/50 p-4">
          <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">
            {job.merged_output || "Result pending."}
          </p>
        </div>

        <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
          <p>Nodes used: {job.assigned_node_ids.join(", ") || "-"}</p>
          <p>Latency: {Math.round(job.metrics.total_ms || 0)} ms</p>
          <p>Confidence: {(job.verification_confidence * 100).toFixed(1)}%</p>
          <p>Status: {job.status}</p>
        </div>
      </Card>

      <Card>
        <h3 className="mb-3 text-sm font-semibold text-foreground">Replica Output Diff</h3>
        <div className="grid gap-3 lg:grid-cols-2">
          {job.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No node outputs available yet.</p>
          ) : (
            job.results.map((result) => (
              <div key={result.node_id} className="rounded-xl border border-border bg-background/40 p-3">
                <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                  {result.node_id} {result.success ? "" : "(failed)"}
                </p>
                <p className="whitespace-pre-wrap text-sm text-foreground">
                  {result.success ? result.output : result.error}
                </p>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
