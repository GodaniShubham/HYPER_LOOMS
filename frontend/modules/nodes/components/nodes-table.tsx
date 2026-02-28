import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { TD, TH, TBody, THead, Table } from "@/components/ui/table";
import { NodeModel } from "@/types/node";

type NodesTableProps = {
  nodes: NodeModel[];
};

function statusTone(status: NodeModel["status"]): "success" | "warning" | "danger" {
  if (status === "healthy") {
    return "success";
  }
  if (status === "busy") {
    return "warning";
  }
  return "danger";
}

export function NodesTable({ nodes }: NodesTableProps): JSX.Element {
  return (
    <Card>
      <h3 className="mb-4 text-sm font-semibold text-foreground">Fabric Nodes</h3>
      <div className="overflow-x-auto">
        <Table>
          <THead>
            <tr>
              <TH>Node</TH>
              <TH>GPU</TH>
              <TH>VRAM</TH>
              <TH>Status</TH>
              <TH>Trust</TH>
              <TH>Jobs</TH>
            </tr>
          </THead>
          <TBody>
            {nodes.map((node) => (
              <tr key={node.id} className="hover:bg-white/5">
                <TD className="font-medium text-foreground">{node.id}</TD>
                <TD>{node.gpu}</TD>
                <TD>
                  {node.vram_used_gb.toFixed(1)} / {node.vram_total_gb.toFixed(0)} GB
                </TD>
                <TD>
                  <Badge tone={statusTone(node.status)}>{node.status}</Badge>
                </TD>
                <TD>{(node.trust_score * 100).toFixed(1)}%</TD>
                <TD>{node.jobs_running}</TD>
              </tr>
            ))}
          </TBody>
        </Table>
      </div>
    </Card>
  );
}
