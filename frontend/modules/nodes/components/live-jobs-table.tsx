import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { TD, TH, TBody, THead, Table } from "@/components/ui/table";
import { AdminLiveJobItem } from "@/types/api";

type LiveJobsTableProps = {
  jobs: AdminLiveJobItem[];
};

function tone(status: AdminLiveJobItem["status"]): "success" | "warning" | "danger" | "neutral" {
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

export function LiveJobsTable({ jobs }: LiveJobsTableProps): JSX.Element {
  return (
    <Card>
      <h3 className="mb-4 text-sm font-semibold text-foreground">Live Runs & Replica Splits</h3>
      <div className="overflow-x-auto">
        <Table>
          <THead>
            <tr>
              <TH>Job</TH>
              <TH>Status</TH>
              <TH>Splits</TH>
              <TH>Verification</TH>
              <TH>Trust Signal</TH>
            </tr>
          </THead>
          <TBody>
            {jobs.length === 0 ? (
              <tr>
                <TD className="text-muted-foreground" colSpan={5}>
                  No active jobs.
                </TD>
              </tr>
            ) : (
              jobs.map((job) => (
                <tr key={job.job_id} className="hover:bg-white/5">
                  <TD>
                    <p className="font-medium text-foreground">{job.job_id}</p>
                    <p className="text-xs text-muted-foreground">{job.prompt_preview}</p>
                  </TD>
                  <TD>
                    <Badge tone={tone(job.status)}>{job.status}</Badge>
                  </TD>
                  <TD className="text-xs text-muted-foreground">
                    <p>
                      {job.successful_replicas + job.inflight_replicas}/{job.target_replicas} replicas
                    </p>
                    <p>inflight: {job.inflight_replicas}</p>
                    <p>failed: {job.failed_node_ids.length}</p>
                  </TD>
                  <TD className="text-xs text-muted-foreground">
                    <p>{job.verification_status}</p>
                    <p>{(job.verification_confidence * 100).toFixed(0)}% confidence</p>
                  </TD>
                  <TD className="text-xs text-muted-foreground">
                    <p>nodes: {job.assigned_node_ids.length}</p>
                    <p>model: {job.model}</p>
                  </TD>
                </tr>
              ))
            )}
          </TBody>
        </Table>
      </div>
    </Card>
  );
}
