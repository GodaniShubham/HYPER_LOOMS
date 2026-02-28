"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Cpu, Database, Rocket, ShieldCheck, Timer } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getNetworkSnapshot, getNetworkStats } from "@/services/api/network";
import { NetworkSnapshot } from "@/types/api";
import { useNetworkStream } from "@/modules/nodes/hooks/use-network-stream";
import { NetworkStatsGrid } from "@/modules/nodes/components/network-stats-grid";
import { useRuntimeState } from "@/hooks/use-runtime-state";

const launchStages = [
  {
    title: "Model Intake",
    description: "Upload base model reference, target task, and dataset profile.",
    icon: Database,
  },
  {
    title: "Compute Provisioning",
    description: "Allocate replicas across trusted nodes by VRAM, trust, and region.",
    icon: Cpu,
  },
  {
    title: "Consensus Verification",
    description: "Outputs are replica-verified before release to production.",
    icon: ShieldCheck,
  },
  {
    title: "Release Pipeline",
    description: "Promote validated artifacts to startup staging or customer delivery.",
    icon: Rocket,
  },
];

export function ControlPage(): JSX.Element {
  const runtime = useRuntimeState();
  const [snapshot, setSnapshot] = useState<NetworkSnapshot | undefined>(undefined);
  const handleNetworkUpdate = useCallback((nextSnapshot: NetworkSnapshot) => {
    setSnapshot(nextSnapshot);
  }, []);
  const networkStream = useNetworkStream(handleNetworkUpdate);

  const statsQuery = useQuery({
    queryKey: ["network-stats"],
    queryFn: getNetworkStats,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive ? (networkStream.connected ? 15000 : 9000) : false,
  });

  const snapshotQuery = useQuery({
    queryKey: ["network-snapshot"],
    queryFn: getNetworkSnapshot,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive && !networkStream.connected ? 12000 : false,
  });

  const activeSnapshot = snapshot ?? snapshotQuery.data;

  return (
    <AppShell>
      <div className="space-y-5">
        <Card className="relative overflow-hidden border-primary/35">
          <div className="pointer-events-none absolute -right-10 -top-14 h-44 w-44 rounded-full bg-primary/25 blur-3xl" />
          <div className="pointer-events-none absolute left-16 top-8 h-36 w-36 rounded-full bg-accent/20 blur-3xl" />
          <div className="relative grid gap-4 lg:grid-cols-[1.6fr,1fr]">
            <div className="space-y-4">
              <p className="section-kicker">Startup-Grade AI Compute Marketplace</p>
              <h1 className="max-w-3xl text-3xl font-semibold leading-tight text-foreground md:text-4xl xl:text-5xl">
                Train, fine-tune, and verify models on a decentralized GPU command fabric.
              </h1>
              <p className="max-w-2xl text-sm text-muted-foreground md:text-base">
                Hyperlooms is structured for teams that need instant capacity, policy-based trust verification, and
                operational telemetry before shipping model outputs to customers.
              </p>
              <div className="flex flex-wrap gap-2">
                <Link href="/jobs">
                  <Button>
                    Launch Workload
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/admin">
                  <Button variant="secondary">Open Operations</Button>
                </Link>
              </div>
            </div>
            <div className="grid gap-2 rounded-2xl border border-border/80 bg-black/30 p-3">
              <Badge tone="warning" className="w-fit">
                Fabric Readiness
              </Badge>
              <div className="rounded-xl border border-border/70 bg-background/50 p-3">
                <p className="text-xs text-muted-foreground">Active Nodes</p>
                <p className="text-3xl font-semibold text-foreground">{statsQuery.data?.active_nodes ?? "--"}</p>
              </div>
              <div className="rounded-xl border border-border/70 bg-background/50 p-3">
                <p className="text-xs text-muted-foreground">Live Jobs</p>
                <p className="text-3xl font-semibold text-foreground">{statsQuery.data?.jobs_running ?? "--"}</p>
              </div>
              <div className="flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
                <Timer className="h-3.5 w-3.5" />
                Model verification stream active
              </div>
            </div>
          </div>
        </Card>

        {statsQuery.isLoading ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : statsQuery.data ? (
          <NetworkStatsGrid stats={statsQuery.data} />
        ) : (
          <Card className="text-sm text-danger">Unable to load network stats.</Card>
        )}

        <Card className="space-y-4">
          <div>
            <p className="section-kicker">Execution Flow</p>
            <h2 className="text-xl font-semibold text-foreground">From Model Request To Verified Output</h2>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {launchStages.map((stage) => {
              const Icon = stage.icon;
              return (
                <div key={stage.title} className="rounded-xl border border-border/80 bg-background/45 p-4">
                  <div className="mb-2 inline-flex rounded-lg border border-primary/40 bg-primary/12 p-2 text-primary">
                    <Icon className="h-4 w-4" />
                  </div>
                  <p className="text-sm font-semibold text-foreground">{stage.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{stage.description}</p>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-foreground">Live Node Fabric</h2>
            <Badge tone="neutral">{activeSnapshot?.nodes?.length ?? 0} nodes visible</Badge>
          </div>
          {activeSnapshot?.nodes?.length ? (
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {activeSnapshot.nodes.map((node) => (
                <div key={node.id} className="rounded-xl border border-border bg-background/40 p-3 text-sm">
                  <div className="mb-1 flex items-center justify-between">
                    <p className="font-medium text-foreground">{node.id}</p>
                    <Badge tone={node.status === "healthy" ? "success" : node.status === "busy" ? "warning" : "danger"}>
                      {node.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{node.gpu}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    trust {(node.trust_score * 100).toFixed(0)}% | jobs {node.jobs_running} | VRAM{" "}
                    {node.vram_used_gb.toFixed(1)}/{node.vram_total_gb.toFixed(1)} GB
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No active node feed yet.</p>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
