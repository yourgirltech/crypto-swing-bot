"""
Pydantic response schemas -- Milestone 5/6. Mirror the corresponding
service-layer dataclasses field-for-field (via from_attributes) rather
than redefining the shape independently, so the API contract can never
silently drift from what the service layer actually returns.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_id: int
    symbol: str
    generated_at: datetime
    triggering_candle_time: datetime

    setup_type: str
    direction: str
    trend: str
    regime: str
    rsi: float
    entry_price: float
    stop_price: float
    target_price: float
    reward_risk_ratio: float
    risk_amount: float
    position_size: float
    backtested_win_rate_pct: Optional[float] = None
    backtested_sample_size: Optional[int] = None
    backtested_expectancy_r: Optional[float] = None
    notes: str

    risk_status: str
    risk_verdict_reason: Optional[str] = None
    human_decision: Optional[str] = None
    human_decision_reason: Optional[str] = None
    human_decision_at: Optional[datetime] = None

    paper_trade_id: Optional[int] = None
    paper_trade_status: Optional[str] = None
    data_source: Optional[str] = None
    entry_fill_price: Optional[float] = None
    entry_fee: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    proposed_exit_price: Optional[float] = None
    exit_fill_price: Optional[float] = None
    exit_fee: Optional[float] = None
    outcome: Optional[str] = None
    r_multiple_ideal: Optional[float] = None
    r_multiple_realistic: Optional[float] = None
    pnl_ngn: Optional[float] = None
    approval_summary: Optional[str] = None


class PerformanceStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_closed_trades: int
    win_rate_pct: float
    avg_win_r_realistic: float
    avg_loss_r_realistic: float
    expectancy_r_ideal: float
    expectancy_r_realistic: float
    total_pnl_ngn: float
    total_fees_ngn: float


class EquityPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    equity: float
    pnl_ngn: float
    symbol: str
    outcome: str


class CandleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    rsi: Optional[float] = None


class BacktestSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_trades: int
    win_rate_pct: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float


class RegimeStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    regime: str
    trades: int
    win_rate_pct: float
    expectancy_r: float


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    timeframe: str
    run_at: datetime
    data_source: str
    date_range_start: datetime
    date_range_end: datetime
    params: dict
    summary: BacktestSummaryOut
    regime_breakdown: List[RegimeStatsOut] = []


class CumulativeRPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    r_multiple: float
    cumulative_r: float
    outcome: str
    direction: str


class StrategyInfoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    symbols: List[str]
    parameters: dict


class AccountSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_baseline: float
    account_equity: float
    peak_equity: float
    open_positions_count: int
    daily_pnl_pct: float
    weekly_pnl_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_open_positions: int
    max_drawdown_pct: float


class CorrelatedGroupExposureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbols: List[str]
    notional: float
    exposure_pct: float


class RiskStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_per_trade_pct: float
    max_position_size_pct: float
    max_portfolio_exposure_pct: float
    max_correlated_exposure_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_drawdown_pct: float
    max_open_positions: int
    max_leverage: float
    correlated_groups: List[List[str]]

    account_equity: float
    peak_equity: float
    drawdown_pct: float
    daily_pnl_pct: float
    weekly_pnl_pct: float
    open_positions_count: int
    portfolio_exposure_pct: float
    correlated_exposure: List[CorrelatedGroupExposureOut]


class SystemHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    api_ok: bool
    db_ok: bool
    latest_candle_time: Optional[datetime] = None
    latest_signal_time: Optional[datetime] = None
    configured_poll_interval_seconds: int
    # Explicitly False, not omitted -- see api/routes/system.py's docstring
    # for why these two are genuinely untracked, not just unpopulated.
    retry_events_tracked: bool
    paper_engine_heartbeat_tracked: bool
