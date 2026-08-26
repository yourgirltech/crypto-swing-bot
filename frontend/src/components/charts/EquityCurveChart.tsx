"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/lib/types";
import { formatDateTime, formatNgn } from "@/lib/format";

const GREEN = "#22c55e";
const RED = "#ef4444";
const BORDER = "#232a35";
const MUTED = "#6b7280";

export function EquityCurveChart({ points }: { points: EquityPoint[] }) {
  const first = points[0]?.equity ?? 0;
  const last = points[points.length - 1]?.equity ?? 0;
  const tone = last >= first ? GREEN : RED;

  const data = points.map((p) => ({ ...p, timeLabel: formatDateTime(p.time) }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={tone} stopOpacity={0.25} />
              <stop offset="100%" stopColor={tone} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={BORDER} strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="timeLabel"
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => formatNgn(v)}
            width={90}
          />
          <Tooltip
            contentStyle={{
              background: "#12161d",
              border: `1px solid ${BORDER}`,
              borderRadius: 3,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: MUTED }}
            formatter={(value) => [formatNgn(Number(value)), "Equity"]}
          />
          <Area type="stepAfter" dataKey="equity" stroke={tone} strokeWidth={1.5} fill="url(#equityFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
