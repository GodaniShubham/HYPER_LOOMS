"use client";

import { Activity, LocateFixed } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { NodeModel } from "@/types/node";

type HyperGlobalMapProps = {
  nodes: NodeModel[];
  jobsRunning: number;
};

export function HyperGlobalMap({ nodes, jobsRunning }: HyperGlobalMapProps): JSX.Element {
  const activeServiceNodes = nodes.filter((node) => node.status !== "offline");
  const highlighted = activeServiceNodes.slice(0, 5);

  return (
    <div className="relative h-[500px] overflow-hidden rounded-2xl border border-danger/85 bg-[#090102] shadow-[0_0_0_1px_rgba(255,65,49,0.4),0_24px_64px_rgba(0,0,0,0.65)]">
      <img
        src="/redmap.avif"
        alt="India red neon map"
        className="pointer-events-none absolute inset-0 h-full w-full select-none object-cover object-center"
      />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.35)_0%,rgba(0,0,0,0.2)_60%,rgba(0,0,0,0.5)_100%)]" />

      <div className="absolute left-4 top-4 z-20 space-y-1 pr-24">
        <p className="section-kicker">India Satellite View</p>
        <h3 className="text-lg font-semibold text-foreground">Service Node Command Grid</h3>
        <p className="text-xs text-white/70">Red map rendered directly from `redmap.avif`.</p>
      </div>

      <div className="absolute right-4 top-4 z-20 flex items-center gap-2">
        <Badge tone={jobsRunning > 0 ? "warning" : "neutral"}>{jobsRunning} active jobs</Badge>
        <Badge tone={activeServiceNodes.length > 0 ? "success" : "danger"}>{activeServiceNodes.length} service nodes</Badge>
      </div>

      <div className="absolute bottom-4 left-4 z-20 inline-flex items-center gap-2 rounded-lg border border-danger/70 bg-black/60 px-3 py-1.5 text-xs text-white/85">
        <Activity className="h-3.5 w-3.5 text-primary" />
        {activeServiceNodes.length} / {nodes.length} nodes serving traffic
      </div>

      <div className="absolute bottom-4 right-4 z-20 w-56 rounded-xl border border-danger/70 bg-black/60 p-3">
        <div className="mb-2 inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-orange-300">
          <LocateFixed className="h-3 w-3" />
          Live Node Beacons
        </div>
        <div className="space-y-1.5">
          {highlighted.length ? (
            highlighted.map((node) => (
              <div
                key={`beacon-${node.id}`}
                className="flex items-center justify-between rounded-md border border-white/10 bg-white/[0.03] px-2 py-1"
              >
                <span className="truncate pr-2 text-[11px] text-white/80">{node.id}</span>
                <span className="text-[11px] text-orange-300">{node.jobs_running} svc</span>
              </div>
            ))
          ) : (
            <p className="text-[11px] text-muted-foreground">No active service nodes.</p>
          )}
        </div>
      </div>
    </div>
  );
}
