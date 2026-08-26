"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CumulativeRPoint } from "@/lib/types";
import { formatDateTime, formatR } from "@/lib/format";

const GREEN = "#22c55e";
const BORDER = "#232a35";
const MUTED = "#6b7280";

/**
 * Cumulative R-multiple across a backtest's trade sequence -- NOT a
 * dollar equity curve. See backtest/history.py: per-trade position size
 * was never persisted for backtest_trades, so a ₦ figure here would not
 * match what the original run actually computed. R-multiple is
 * position-size-independent by construction, so this is an exact,
 * honest reconstruction of the trade-by-trade R sequence.
 */
export function CumulativeRChart({ points }: { points: CumulativeRPoint[] }) {
  const data = points.map((p, i) => ({ ...p, index: i + 1, timeLabel: formatDateTime(p.time) }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={BORDER} strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="index"
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            label={{ value: "Trade #", position: "insideBottom", offset: -2, fill: MUTED, fontSize: 10 }}
          />
          <YAxis
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            tickFormatter={(v: number) => `${v}R`}
            width={50}
          />
          <ReferenceLine y={0} stroke={MUTED} strokeDasharray="3 3" />
          <Tooltip
            contentStyle={{
              background: "#12161d",
              border: `1px solid ${BORDER}`,
              borderRadius: 3,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: MUTED }}
            formatter={(value) => [formatR(Number(value), 2), "Cumulative R"]}
            labelFormatter={(_, payload) => (payload?.[0]?.payload ? payload[0].payload.timeLabel : "")}
          />
          <Line type="linear" dataKey="cumulative_r" stroke={GREEN} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
