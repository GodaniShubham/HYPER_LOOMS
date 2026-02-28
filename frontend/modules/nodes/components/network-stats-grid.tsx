import { Card } from "@/components/ui/card";
import { NetworkStats } from "@/types/api";

type NetworkStatsGridProps = {
  stats: NetworkStats;
};

export function NetworkStatsGrid({ stats }: NetworkStatsGridProps): JSX.Element {
  const items = [
    { label: "Active Nodes", value: stats.active_nodes, hint: "healthy + busy" },
    { label: "Total VRAM", value: `${stats.total_vram_gb.toFixed(0)} GB`, hint: "fabric capacity" },
    { label: "Jobs Running", value: stats.jobs_running, hint: "pending + running + verify" },
    { label: "Avg Latency", value: `${stats.avg_latency_ms.toFixed(0)} ms`, hint: "heartbeat weighted" },
  ];

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label} className="space-y-1 border-primary/20">
          <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">{item.label}</p>
          <p className="text-2xl font-semibold text-foreground">{item.value}</p>
          <p className="text-[11px] text-muted-foreground">{item.hint}</p>
        </Card>
      ))}
    </div>
  );
}
