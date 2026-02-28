"use client";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { NetworkStats } from "@/types/api";
import { NodeModel } from "@/types/node";

type HyperOpsRailProps = {
  stats?: NetworkStats;
  nodes: NodeModel[];
};

export function HyperOpsRail({ stats, nodes }: HyperOpsRailProps): JSX.Element {
  const online = nodes.filter((node) => node.status !== "offline").length;
  const running = stats?.jobs_running ?? 0;
  const connectedGpus = nodes.length;

  return (
    <Card className="space-y-4 border-border/80 bg-[#0a0f18]/90 p-3">
      <div className="rounded-xl border border-success/40 bg-success/15 p-3">
        <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Real-Time Inference Status</p>
        <p className="mt-1 text-2xl font-semibold text-success">{running > 0 ? "Active" : "Idle"}</p>
        <p className="text-xs text-muted-foreground">{online} online nodes streaming</p>
      </div>

      <div className="rounded-xl border border-primary/40 bg-primary/12 p-3">
        <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Connected GPUs</p>
        <p className="mt-1 text-2xl font-semibold text-primary">{connectedGpus.toLocaleString()}</p>
        <p className="text-xs text-muted-foreground">fabric-visible compute nodes</p>
      </div>

      <div className="flex items-center justify-between rounded-lg border border-border/80 bg-black/30 px-3 py-2">
        <span className="text-xs text-muted-foreground">Cluster posture</span>
        <Badge tone={online > 0 ? "success" : "danger"}>{online > 0 ? "online" : "offline"}</Badge>
      </div>
    </Card>
  );
}
