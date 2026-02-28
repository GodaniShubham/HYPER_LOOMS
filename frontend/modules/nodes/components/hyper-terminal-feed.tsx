"use client";

import { useEffect, useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { AdminLiveJobItem, NetworkStats } from "@/types/api";
import { NodeModel } from "@/types/node";

type HyperTerminalFeedProps = {
  jobs: AdminLiveJobItem[];
  nodes: NodeModel[];
  stats?: NetworkStats;
};

export function HyperTerminalFeed({ jobs, nodes, stats }: HyperTerminalFeedProps): JSX.Element {
  const [clock, setClock] = useState("--:--:--");

  useEffect(() => {
    const refreshClock = () => {
      setClock(new Date().toLocaleTimeString("en-US", { hour12: false }));
    };
    refreshClock();
    const interval = window.setInterval(refreshClock, 5000);
    return () => window.clearInterval(interval);
  }, []);

  const lines = useMemo(() => {
    const heartbeat = `[${clock}] heartbeat sync :: nodes=${stats?.active_nodes ?? 0} jobs=${stats?.jobs_running ?? 0}`;
    const nodeLines = nodes.slice(0, 4).map((node) => {
      const mode = node.status === "busy" ? "dispatching" : node.status === "healthy" ? "ready" : "offline";
      return `[${clock}] node/${node.id} :: ${mode} :: trust=${(node.trust_score * 100).toFixed(0)}%`;
    });
    const jobLines = jobs.slice(0, 6).map((job) => {
      return `[${clock}] job/${job.job_id} :: ${job.status} :: verify=${(job.verification_confidence * 100).toFixed(0)}%`;
    });
    const rotator = Number(clock.split(":").at(-1) ?? 0) % 2 === 0 ? "fabric consensus stream open" : "replica quorum trace updated";
    return [`[${clock}] ${rotator}`, heartbeat, ...jobLines, ...nodeLines].slice(0, 12);
  }, [clock, jobs, nodes, stats?.active_nodes, stats?.jobs_running]);

  return (
    <Card className="space-y-3 border-border/80 bg-[#090e17]/90 p-4">
      <div>
        <p className="section-kicker">Terminal</p>
        <h3 className="text-base font-semibold text-foreground">Live Execution Stream</h3>
      </div>
      <div className="rounded-xl border border-border/80 bg-[#050911] p-3 font-mono text-xs leading-6">
        {lines.map((line, index) => (
          <p key={`${line}-${index}`} className="text-muted-foreground">
            <span className="text-primary">//</span> {line}
          </p>
        ))}
        <p className="animate-pulse text-success">_</p>
      </div>
    </Card>
  );
}
