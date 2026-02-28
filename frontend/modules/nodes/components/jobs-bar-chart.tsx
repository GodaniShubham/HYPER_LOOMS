"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { NodeJobDistributionItem } from "@/types/api";

type JobsBarChartProps = {
  data: NodeJobDistributionItem[];
};

export function JobsBarChart({ data }: JobsBarChartProps): JSX.Element {
  return (
    <Card>
      <h3 className="mb-4 text-sm font-semibold text-foreground">Replica Load Graph</h3>
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <XAxis dataKey="node_id" stroke="#c7bfb9" tick={{ fontSize: 11 }} />
            <YAxis stroke="#c7bfb9" allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{
                background: "rgba(26, 13, 10, 0.96)",
                border: "1px solid rgba(255, 114, 56, 0.3)",
                borderRadius: 12,
              }}
            />
            <Bar dataKey="jobs" fill="hsl(8 97% 57%)" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
