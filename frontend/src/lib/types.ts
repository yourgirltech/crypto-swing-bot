/**
 * Mirrors api/schemas.py field-for-field. Keep in sync by hand -- this is
 * a two-service project (Python backend, TS frontend), not a monorepo
 * with shared codegen, so there's no automatic contract check. If a field
 * here doesn't match the backend, requests still succeed (FastAPI doesn't
 * know about this file) but data will silently come through as undefined.
 */

export type RiskStatus = "pending" | "approved" | "rejected";
export type HumanDecisionValue = "approved" | "declined";
export type PaperTradeStatus = "open" | "closed";
export type Outcome = "win" | "loss";
export type Direction = "long" | "short";

export interface JournalEntry {
  signal_id: number;
  symbol: string;
  generated_at: string;
  triggering_candle_time: string;

  setup_type: string;
  direction: Direction;
  trend: string;
  regime: string;
  rsi: number;
  entry_price: number;
  stop_price: number;
  target_price: number;
  reward_risk_ratio: number;
  risk_amount: number;
  position_size: number;
  backtested_win_rate_pct: number | null;
  backtested_sample_size: number | null;
  backtested_expectancy_r: number | null;
  notes: string;

  risk_status: RiskStatus;
  risk_verdict_reason: string | null;
  human_decision: HumanDecisionValue | null;
  human_decision_reason: string | null;
  human_decision_at: string | null;

  paper_trade_id: number | null;
  paper_trade_status: PaperTradeStatus | null;
  data_source: string | null;
  entry_fill_price: number | null;
  entry_fee: number | null;
  entry_time: string | null;
  exit_time: string | null;
  proposed_exit_price: number | null;
  exit_fill_price: number | null;
  exit_fee: number | null;
  outcome: Outcome | null;
  r_multiple_ideal: number | null;
  r_multiple_realistic: number | null;
  pnl_ngn: number | null;
  approval_summary: string | null;
}

export interface PerformanceStats {
  total_closed_trades: number;
  win_rate_pct: number;
  avg_win_r_realistic: number;
  avg_loss_r_realistic: number;
  expectancy_r_ideal: number;
  expectancy_r_realistic: number;
  total_pnl_ngn: number;
  total_fees_ngn: number;
}

export interface BacktestSummary {
  total_trades: number;
  win_rate_pct: number;
  avg_win_r: number;
  avg_loss_r: number;
  expectancy_r: number;
}

export interface RegimeStats {
  regime: string;
  trades: number;
  win_rate_pct: number;
  expectancy_r: number;
}

export interface BacktestRun {
  id: number;
  symbol: string;
  timeframe: string;
  run_at: string;
  data_source: string;
  date_range_start: string;
  date_range_end: string;
  params: Record<string, unknown>;
  summary: BacktestSummary;
  regime_breakdown: RegimeStats[];
}

export interface StrategyInfo {
  name: string;
  description: string;
  symbols: string[];
  parameters: Record<string, unknown>;
}

export interface EquityPoint {
  time: string;
  equity: number;
  pnl_ngn: number;
  symbol: string;
  outcome: string;
}

export interface Candle {
  open_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  ema_fast: number | null;
  ema_slow: number | null;
  rsi: number | null;
}

export interface CumulativeRPoint {
  time: string;
  r_multiple: number;
  cumulative_r: number;
  outcome: string;
  direction: string;
}

export interface AccountSummary {
  account_baseline: number;
  account_equity: number;
  peak_equity: number;
  open_positions_count: number;
  daily_pnl_pct: number;
  weekly_pnl_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  max_open_positions: number;
  max_drawdown_pct: number;
}

export interface CorrelatedGroupExposure {
  symbols: string[];
  notional: number;
  exposure_pct: number;
}

export interface RiskState {
  risk_per_trade_pct: number;
  max_position_size_pct: number;
  max_portfolio_exposure_pct: number;
  max_correlated_exposure_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  max_drawdown_pct: number;
  max_open_positions: number;
  max_leverage: number;
  correlated_groups: string[][];

  account_equity: number;
  peak_equity: number;
  drawdown_pct: number;
  daily_pnl_pct: number;
  weekly_pnl_pct: number;
  open_positions_count: number;
  portfolio_exposure_pct: number;
  correlated_exposure: CorrelatedGroupExposure[];
}

export interface SystemHealth {
  api_ok: boolean;
  db_ok: boolean;
  latest_candle_time: string | null;
  latest_signal_time: string | null;
  configured_poll_interval_seconds: number;
  retry_events_tracked: boolean;
  paper_engine_heartbeat_tracked: boolean;

  recent_retry_events: RetryEvent[];
  retry_count_recent: number;
  retry_lookback_minutes: number;
  retry_elevated_threshold: number;
  retry_health: "clean" | "elevated";

  paper_engine_status: "running" | "stale" | "not_running";
  paper_engine_detail: string;
  latest_heartbeat_at: string | null;
  heartbeat_stale_threshold_minutes: number;
}

export interface RetryEvent {
  occurred_at: string;
  source: string;
  request_desc: string;
  attempt_number: number;
  max_attempts: number;
  delay_seconds: number;
  exception_type: string;
  exception_message: string;
}
