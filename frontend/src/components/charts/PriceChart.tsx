"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candle } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

const GREEN = "#22c55e";
const RED = "#ef4444";
const AMBER = "#f59e0b";
const BORDER = "#232a35";
const MUTED = "#6b7280";
const PRIMARY = "#e6e9ef";

interface CandleShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: Candle;
}

/**
 * Recharts has no built-in candlestick chart type. This renders one via a
 * Bar whose dataKey is the [low, high] range (so Recharts' scale maps the
 * bar's pixel y/height to that range), then derives the open/close body's
 * pixel position from that same scale inside the custom shape.
 */
function CandleShape(props: CandleShapeProps) {
  const { x, y, width, height, payload } = props;
  if (x === undefined || y === undefined || width === undefined || height === undefined || !payload) {
    return null;
  }
  const { open, close, high, low } = payload;
  const isUp = close >= open;
  const color = isUp ? GREEN : RED;
  const range = high - low || 1;
  const pxPerUnit = height / range;
  const openY = y + (high - open) * pxPerUnit;
  const closeY = y + (high - close) * pxPerUnit;
  const bodyY = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 1);
  const wickX = x + width / 2;
  const bodyWidth = Math.max(width * 0.6, 1);
  const bodyX = x + (width - bodyWidth) / 2;

  return (
    <g>
      <line x1={wickX} y1={y} x2={wickX} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={bodyX} y={bodyY} width={bodyWidth} height={bodyHeight} fill={color} />
    </g>
  );
}

export interface TradeMarkers {
  entry_price: number;
  stop_price: number;
  target_price: number;
  direction: "long" | "short";
}

export function PriceChart({ candles, markers }: { candles: Candle[]; markers?: TradeMarkers }) {
  const data = candles.map((c) => ({ ...c, range: [c.low, c.high], timeLabel: formatDateTime(c.open_time) }));

  return (
    <div className="h-80 w-full">
      {/*
        minWidth/minHeight matter, not just belt-and-suspenders: Recharts'
        ResponsiveContainer renders its inner wrapper at a literal
        width:0;height:0 until a ResizeObserver reports the real measured
        size of the OUTER container -- on some Next.js hydration timings
        that observer callback never fires, leaving the chart permanently
        at 0x0 (no error, just nothing drawn) even though the outer div
        already has the correct h-80/w-full size. These props put a real
        floor under the size Recharts starts from, so there's always
        something to render before/without the observer ever firing.
      */}
      <ResponsiveContainer width="100%" height="100%" minWidth={300} minHeight={320}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={BORDER} strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="timeLabel"
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            minTickGap={60}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: MUTED, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: BORDER }}
            tickLine={false}
            width={70}
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
            formatter={(value, name) => {
              if (name === "range") return [null, null];
              return [typeof value === "number" ? value.toFixed(2) : String(value ?? ""), String(name ?? "")];
            }}
          />
          <Bar dataKey="range" shape={CandleShape} isAnimationActive={false} />
          <Line
            type="monotone"
            dataKey="ema_fast"
            name="EMA 21"
            stroke={AMBER}
            strokeWidth={1.25}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ema_slow"
            name="EMA 50"
            stroke={PRIMARY}
            strokeWidth={1.25}
            dot={false}
            isAnimationActive={false}
          />
          {markers && (
            <ReferenceLine
              y={markers.entry_price}
              stroke={PRIMARY}
              strokeDasharray="4 3"
              label={{ value: "Entry", position: "insideTopLeft", fill: PRIMARY, fontSize: 10 }}
            />
          )}
          {markers && (
            <ReferenceLine
              y={markers.stop_price}
              stroke={RED}
              strokeDasharray="4 3"
              label={{ value: "Stop", position: "insideTopLeft", fill: RED, fontSize: 10 }}
            />
          )}
          {markers && (
            <ReferenceLine
              y={markers.target_price}
              stroke={GREEN}
              strokeDasharray="4 3"
              label={{ value: "Target", position: "insideTopLeft", fill: GREEN, fontSize: 10 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
