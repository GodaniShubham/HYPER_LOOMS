"use client";

import { useMemo } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { NetworkStats, NodeJobDistributionItem } from "@/types/api";

type HyperSavingsChartProps = {
  stats?: NetworkStats;
  distribution: NodeJobDistributionItem[];
};

type SavingsPoint = {
  step: number;
  hyperlooms: number;
  aws: number;
};

export function HyperSavingsChart({ stats, distribution }: HyperSavingsChartProps): JSX.Element {
  const data = useMemo<SavingsPoint[]>(() => {
    const activeNodes = Math.max(1, stats?.active_nodes ?? 1);
    const runningJobs = Math.max(1, stats?.jobs_running ?? 1);
    const avgJobs = distribution.length ? distribution.reduce((acc, item) => acc + item.jobs, 0) / distribution.length : 1;

    return [0, 10, 20, 30, 40, 50, 60, 70].map((step) => {
      const aws = 12 + step * (1.1 + activeNodes * 0.01) + runningJobs * 1.4 + avgJobs * 3.8;
      const hyperlooms = 8 + step * (0.68 + activeNodes * 0.008) + runningJobs * 0.84 + avgJobs * 2.1;
      return {
        step,
        aws: Number(aws.toFixed(2)),
        hyperlooms: Number(hyperlooms.toFixed(2)),
      };
    });
  }, [distribution, stats?.active_nodes, stats?.jobs_running]);

  const latest = data[data.length - 1];
  const savingsPct = latest ? ((latest.aws - latest.hyperlooms) / latest.aws) * 100 : 0;

  return (
    <Card className="space-y-3 border-border/80 bg-[#0b101a]/90 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-foreground">Cost Savings vs AWS</h3>
        <span className="rounded-lg border border-primary/60 bg-primary/18 px-2 py-1 text-xs font-semibold text-primary">
          {savingsPct.toFixed(0)}% savings
        </span>
      </div>

      <div className="h-[245px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <XAxis dataKey="step" stroke="#97a4bd" tick={{ fontSize: 11 }} tickLine={false} />
            <YAxis stroke="#97a4bd" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{
                background: "rgba(7, 11, 20, 0.96)",
                border: "1px solid rgba(255, 110, 64, 0.35)",
                borderRadius: 10,
                color: "#e5ecf8",
              }}
            />
            <Line
              type="monotone"
              dataKey="hyperlooms"
              stroke="hsl(8 97% 57%)"
              strokeWidth={2.5}
              dot={{ r: 2 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="aws"
              stroke="#b7c0cd"
              strokeWidth={2.2}
              strokeDasharray="5 5"
              dot={{ r: 1.8 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
