/**
 * Typed client for the FastAPI backend (api/main.py, Milestones 5-6).
 * Server-only -- called from Server Components, so API_BASE_URL never
 * needs the NEXT_PUBLIC_ prefix (it's not read in the browser).
 *
 * No caching: `cache: "no-store"` on every request. This is a live-ish
 * trading dashboard -- stale cached numbers (open positions, P&L) would
 * be actively misleading, not just a minor staleness tradeoff.
 */

import type {
  AccountSummary,
  BacktestRun,
  Candle,
  CumulativeRPoint,
  EquityPoint,
  JournalEntry,
  PerformanceStats,
  StrategyInfo,
} from "./types";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8010";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function listJournalEntries(params?: {
  symbol?: string;
  risk_status?: string;
  human_decision?: string;
  outcome?: string;
  limit?: number;
}): Promise<JournalEntry[]> {
  const qs = new URLSearchParams();
  if (params?.symbol) qs.set("symbol", params.symbol);
  if (params?.risk_status) qs.set("risk_status", params.risk_status);
  if (params?.human_decision) qs.set("human_decision", params.human_decision);
  if (params?.outcome) qs.set("outcome", params.outcome);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<JournalEntry[]>(`/journal${suffix}`);
}

export function getOpenPositions(): Promise<JournalEntry[]> {
  return apiGet<JournalEntry[]>("/journal/open");
}

export function getPerformanceStats(symbol?: string): Promise<PerformanceStats> {
  const suffix = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  return apiGet<PerformanceStats>(`/journal/performance${suffix}`);
}

export function listBacktestRuns(params?: { symbol?: string; limit?: number }): Promise<BacktestRun[]> {
  const qs = new URLSearchParams();
  if (params?.symbol) qs.set("symbol", params.symbol);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiGet<BacktestRun[]>(`/backtests${suffix}`);
}

export function getBacktestRun(runId: number): Promise<BacktestRun> {
  return apiGet<BacktestRun>(`/backtests/${runId}`);
}

export function listStrategies(): Promise<StrategyInfo[]> {
  return apiGet<StrategyInfo[]>("/strategies");
}

export function getAccountSummary(): Promise<AccountSummary> {
  return apiGet<AccountSummary>("/account");
}

export function getEquityCurve(symbol?: string): Promise<EquityPoint[]> {
  const suffix = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  return apiGet<EquityPoint[]>(`/journal/equity-curve${suffix}`);
}

export function getCandles(params: {
  symbol: string;
  timeframe?: string;
  source?: string;
  limit?: number;
}): Promise<Candle[]> {
  const qs = new URLSearchParams({ symbol: params.symbol });
  if (params.timeframe) qs.set("timeframe", params.timeframe);
  if (params.source) qs.set("source", params.source);
  if (params.limit) qs.set("limit", String(params.limit));
  return apiGet<Candle[]>(`/market/candles?${qs.toString()}`);
}

export function getCumulativeRCurve(runId: number): Promise<CumulativeRPoint[]> {
  return apiGet<CumulativeRPoint[]>(`/backtests/${runId}/cumulative-r`);
}
