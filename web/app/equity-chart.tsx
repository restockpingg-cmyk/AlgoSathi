"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/lib/analytics";

export function EquityChart({ points }: { points: EquityPoint[] }) {
  const data = points.map((p) => ({
    timestamp: new Date(p.timestamp).toLocaleString(),
    pnl: Number(p.cumulativeRealizedPnl.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="timestamp" tick={{ fontSize: 11, fill: "#a1a1aa" }} minTickGap={40} />
        <YAxis tick={{ fontSize: 11, fill: "#a1a1aa" }} width={70} />
        <Tooltip
          contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", fontSize: 12 }}
          labelStyle={{ color: "#e4e4e7" }}
        />
        <Line
          type="stepAfter"
          dataKey="pnl"
          stroke="#34d399"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
