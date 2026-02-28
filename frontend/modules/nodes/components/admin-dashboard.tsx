"use client";

import { useCallback, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getJobStatusCounts,
  getJobsDistribution,
  getLiveJobs,
  getLocalRegisteredNode,
  registerLocalAdminNode,
} from "@/services/api/admin";
import { getNetworkSnapshot, getNetworkStats } from "@/services/api/network";
import { NetworkSnapshot, NetworkStats } from "@/types/api";
import { NodeModel } from "@/types/node";
import { HyperGlobalMap } from "@/modules/nodes/components/hyper-global-map";
import { HyperOpsRail } from "@/modules/nodes/components/hyper-ops-rail";
import { HyperSavingsChart } from "@/modules/nodes/components/hyper-savings-chart";
import { HyperTerminalFeed } from "@/modules/nodes/components/hyper-terminal-feed";
import { LiveJobsTable } from "@/modules/nodes/components/live-jobs-table";
import { NetworkStatsGrid } from "@/modules/nodes/components/network-stats-grid";
import { NodesTable } from "@/modules/nodes/components/nodes-table";
import { useNetworkStream } from "@/modules/nodes/hooks/use-network-stream";
import { useRuntimeState } from "@/hooks/use-runtime-state";

export function AdminDashboard(): JSX.Element {
  const queryClient = useQueryClient();
  const runtime = useRuntimeState();
  const [liveNodes, setLiveNodes] = useState<NodeModel[] | undefined>(undefined);
  const [registerInfo, setRegisterInfo] = useState<string>("");
  const handleNetworkUpdate = useCallback((snapshot: NetworkSnapshot) => {
    setLiveNodes(snapshot.nodes);
  }, []);
  const networkStream = useNetworkStream(handleNetworkUpdate);

  const statsQuery = useQuery({
    queryKey: ["admin-network-stats"],
    queryFn: getNetworkStats,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive ? (networkStream.connected ? 15000 : 8000) : false,
  });
  const snapshotQuery = useQuery({
    queryKey: ["admin-network-snapshot"],
    queryFn: getNetworkSnapshot,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive && !networkStream.connected ? 12000 : false,
  });
  const distributionQuery = useQuery({
    queryKey: ["admin-jobs-distribution"],
    queryFn: getJobsDistribution,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive ? 12000 : false,
  });
  const statusCountsQuery = useQuery({
    queryKey: ["admin-job-status-counts"],
    queryFn: getJobStatusCounts,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive ? 12000 : false,
  });
  const liveJobsQuery = useQuery({
    queryKey: ["admin-live-jobs"],
    queryFn: getLiveJobs,
    enabled: runtime.isOnline,
    refetchInterval: runtime.isInteractive ? ((statsQuery.data?.jobs_running ?? 0) > 0 ? 6000 : 12000) : false,
  });
  const localNodeQuery = useQuery({
    queryKey: ["admin-local-registered-node"],
    queryFn: getLocalRegisteredNode,
    refetchInterval: runtime.isInteractive ? 20000 : false,
  });
  const registerNodeMutation = useMutation({
    mutationFn: () => registerLocalAdminNode(),
    onSuccess: async (node) => {
      setLiveNodes((previous) => {
        const base = previous ?? snapshotQuery.data?.nodes ?? [];
        const merged = [...base.filter((item) => item.id !== node.id), node];
        return merged.sort((left, right) => left.id.localeCompare(right.id));
      });
      setRegisterInfo(`registered ${node.id}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-network-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-network-snapshot"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-jobs-distribution"] }),
      ]);
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "registration_failed";
      setRegisterInfo(`register_failed: ${message}`);
    },
  });

  const remoteNodes = liveNodes ?? snapshotQuery.data?.nodes ?? [];
  const fallbackNodes = localNodeQuery.data ? [localNodeQuery.data] : [];
  const nodes = remoteNodes.length > 0 ? remoteNodes : fallbackNodes;
  const stats: NetworkStats = useMemo(() => {
    if (statsQuery.data) {
      return statsQuery.data;
    }
    const totalVram = nodes.reduce((sum, item) => sum + (item.vram_total_gb || 0), 0);
    const active = nodes.filter((item) => item.status !== "offline").length;
    const avgLatency =
      nodes.length > 0 ? nodes.reduce((sum, item) => sum + (item.latency_ms_avg || 0), 0) / nodes.length : 0;
    return {
      active_nodes: active,
      total_nodes: nodes.length,
      total_vram_gb: totalVram,
      jobs_running: nodes.reduce((sum, item) => sum + (item.jobs_running || 0), 0),
      avg_latency_ms: avgLatency,
    };
  }, [nodes, statsQuery.data]);

  const totalJobs = useMemo(
    () => distributionQuery.data?.reduce((acc, item) => acc + item.jobs, 0) ?? 0,
    [distributionQuery.data]
  );
  const liveJobs = liveJobsQuery.data ?? [];

  return (
    <AppShell>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="section-kicker">Hyperlooms Console</p>
            <h1 className="text-2xl font-semibold text-foreground">Real-Time Inference Operations Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Track global node traffic, inference activity, and cost intelligence from one command surface.
            </p>
            {registerInfo ? <p className="mt-1 text-xs text-muted-foreground">{registerInfo}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              disabled={registerNodeMutation.isPending}
              onClick={() => registerNodeMutation.mutate()}
            >
              {registerNodeMutation.isPending ? "Registering..." : "Register Local Node"}
            </Button>
            {remoteNodes.length === 0 && fallbackNodes.length > 0 ? (
              <Badge tone="warning">Local Node Fallback</Badge>
            ) : null}
            <Badge tone="warning">Admin API Key Mode</Badge>
            <Badge tone="neutral">{nodes.length} tracked nodes</Badge>
          </div>
        </div>

        {statsQuery.isLoading && !statsQuery.data ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <NetworkStatsGrid stats={stats} />
        )}

        <div className="grid gap-4 xl:grid-cols-[220px,1.5fr,1fr]">
          <HyperOpsRail stats={stats} nodes={nodes} />

          <div className="space-y-4">
            <HyperGlobalMap nodes={nodes} jobsRunning={stats.jobs_running} />
          </div>

          <div className="space-y-4">
            <HyperTerminalFeed jobs={liveJobs} nodes={nodes} stats={stats} />
            <HyperSavingsChart stats={stats} distribution={distributionQuery.data ?? []} />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.45fr,1fr]">
          <NodesTable nodes={nodes} />
          <LiveJobsTable jobs={liveJobs} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr,1fr]">
          <Card className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Status Breakdown</h3>
            {statusCountsQuery.data?.length ? (
              statusCountsQuery.data.map((item) => (
                <div key={item.status} className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2">
                  <span className="text-sm text-muted-foreground">{item.status}</span>
                  <span className="text-sm font-semibold text-foreground">{item.count}</span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No job metrics yet.</p>
            )}
            <div className="rounded-lg border border-border bg-background/35 px-3 py-2 text-xs text-muted-foreground">
              Total assigned replicas: {totalJobs}
            </div>
          </Card>

          <Card className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Node Load Pulse</h3>
            {distributionQuery.isLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : distributionQuery.data?.length ? (
              distributionQuery.data.slice(0, 8).map((item) => (
                <div key={item.node_id} className="rounded-lg border border-border/80 bg-black/30 px-3 py-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{item.node_id}</span>
                    <span>{item.jobs} jobs</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${Math.min(100, item.jobs * 22 + 6)}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No node load data yet.</p>
            )}
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
