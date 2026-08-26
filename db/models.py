"""
SQLAlchemy models — Milestone 1 persistence layer.

Deliberately minimal: every column here maps directly to a field already
produced by existing code (Trade / TradeProposal dataclasses, or the OHLCV
DataFrame from data/okx_client.py & data/bybit_client.py). Tables from the
fuller MASTER_PLAN.md §6 list with no current producer (orders, positions,
portfolios, strategies, model_predictions, trading_decisions, system_events,
errors) are intentionally NOT built yet — add them when the engine that
produces their data actually exists (see MASTER_PLAN.md milestones).

Design notes (see conversation history / docs for full reasoning):
- `backtest_runs` isn't in MASTER_PLAN's table list but is needed for
  reproducibility — without it, `backtest_trades` rows have no record of
  which config (history length, filter on/off, risk params) produced them.
- `backtest_runs.params` is JSONB rather than individual columns:
  run_backtest()'s parameter list already changed once (entry_filter was
  just added) — JSONB avoids a migration every time the engine gains a knob.
- `backtest_trades` (not `trades`) — named to avoid a clash with a future
  paper/live trades table (Milestone 4/12), which will need different
  fields (fills, fees, order refs) that don't exist yet.
- `signals.status` reflects the RISK ENGINE's verdict (Milestone 2), not a
  human decision — `signals.human_decision` (Milestone 4) is a separate,
  orthogonal field for that, since a risk-engine REJECT is never even
  shown to a human for a decision (see paper_trading/engine.py).
- Candle indicator values (EMA/RSI/ATR) are NOT persisted — indicators.py
  recomputes them from OHLCV on demand; storing them too would risk
  stale/duplicated data for no current benefit.
- `paper_trades` (Milestone 4) is its own table, not reused from
  `backtest_trades` — this is exactly the "different fields (fills, fees,
  order refs)" case anticipated when `backtest_trades` was named to avoid
  a future clash.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Asset(Base):
    """
    A trading pair (e.g. BTCUSDT), independent of which exchange candle
    data was pulled from — that's tracked per-row on Candle.source, since
    the same pair's data differs slightly by exchange (see okx_client.py
    docstring / docs/ARCHITECTURE.md).
    """
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)   # "BTCUSDT"
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)              # documented execution exchange, e.g. "bybit"
    category: Mapped[str] = mapped_column(String(20), nullable=False)              # "spot" | "linear"

    candles: Mapped[list["Candle"]] = relationship(back_populates="asset")
    backtest_runs: Mapped[list["BacktestRun"]] = relationship(back_populates="asset")
    signals: Mapped[list["Signal"]] = relationship(back_populates="asset")


class Candle(Base):
    """1:1 with the DataFrame columns OKXClient/BybitClient already return."""
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "open_time", "source", name="uq_candle_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)  # Bybit-style: "240" (4H), "D" (daily)
    open_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    turnover: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "okx" | "bybit" — data differs slightly by exchange

    asset: Mapped["Asset"] = relationship(back_populates="candles")


class BacktestRun(Base):
    """
    One execution of run_backtest() — the config fingerprint that makes
    backtest_trades rows reproducible/comparable across parameter changes.
    """
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)  # "okx" | "bybit"
    date_range_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    date_range_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # risk_per_trade_pct, atr_stop_mult, reward_risk, swing_lookback, rsi_extreme,
    # entry_filter_name, starting_balance, etc. — see run_backtest()'s signature.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="backtest_runs")
    trades: Mapped[list["BacktestTrade"]] = relationship(back_populates="run")


class BacktestTrade(Base):
    """
    1:1 with backtest_engine.Trade, minus entry_index/exit_index (those are
    row-positions in a specific in-memory DataFrame slice, not a stable
    identity once persisted — entry_time is the real identity).
    """
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False)

    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)  # "long" | "short"
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "win" | "loss"
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Entry-time diagnostics (see backtest_engine._entry_diagnostics) —
    # what made the weak_bull_trend investigation possible; kept for the
    # next regime/setup investigation too.
    rsi_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_pct_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_from_ema_fast_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_from_ema_slow_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakout_margin_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bars_since_swing: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped["BacktestRun"] = relationship(back_populates="trades")


class SignalStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HumanDecision(enum.Enum):
    """
    A human's decision on a signal the RISK ENGINE already approved. Never
    set for a risk-engine-REJECTED signal — per Milestone 4's design, a
    human is never even shown a setup the risk engine already vetoed.
    """
    APPROVED = "approved"
    DECLINED = "declined"


class Signal(Base):
    """
    1:1 with proposals.trade_proposal.TradeProposal, plus generated_at,
    status (the risk engine's verdict, Milestone 2), and — as of
    Milestone 4 — the human's separate decision on risk-engine-approved
    signals.
    """
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # The open_time of the candle whose close actually triggered this signal
    # (NOT when the row was inserted) — lets the paper trading engine tell
    # "already decided for this candle, still waiting for the next one"
    # apart from "a genuinely new candle closed", across polls AND restarts.
    triggering_candle_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    setup_type: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    reward_risk_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    trend: Mapped[str] = mapped_column(String(20), nullable=False)
    regime: Mapped[str] = mapped_column(String(30), nullable=False)
    rsi: Mapped[float] = mapped_column(Float, nullable=False)
    backtested_win_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    backtested_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backtested_expectancy_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus, name="signal_status"), nullable=False, default=SignalStatus.PENDING
    )
    # Populated by risk.risk_engine.evaluate_trade() (Milestone 2) — the
    # specific rule that failed on REJECTED, or None on APPROVED/PENDING.
    # Without this, status=REJECTED alone doesn't say why.
    risk_verdict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Milestone 4: the human's own decision, separate from the risk engine's
    # verdict above. Only ever populated when status=APPROVED (see
    # HumanDecision docstring) — remains NULL for a risk-engine REJECTED
    # signal, and NULL for an APPROVED one still awaiting a human response.
    human_decision: Mapped[HumanDecision | None] = mapped_column(
        SAEnum(HumanDecision, name="human_decision"), nullable=True
    )
    human_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    asset: Mapped["Asset"] = relationship(back_populates="signals")
    paper_trade: Mapped["PaperTrade | None"] = relationship(back_populates="signal", uselist=False)


class PaperTradeStatus(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class PaperTrade(Base):
    """
    A simulated position opened only after BOTH the risk engine approved a
    Signal AND a human explicitly approved it (Milestone 4) — never an
    auto-execute path. Tracks realistic fill prices (post-slippage, per
    config.BACKTEST.slippage_pct) and fees (config.BACKTEST.fee_pct) on
    both legs, separate from the naive/idealized backtest R-multiple, so
    paper performance can be compared against what the backtest assumed
    (see MASTER_PLAN.md Milestone 4: "realistic execution assumptions...
    vs naive backtest assumptions").
    """
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), nullable=False, unique=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)  # "okx" | "bybit"
    direction: Mapped[str] = mapped_column(String(5), nullable=False)

    proposed_entry_price: Mapped[float] = mapped_column(Float, nullable=False)  # from the TradeProposal, pre-slippage
    entry_fill_price: Mapped[float] = mapped_column(Float, nullable=False)      # after simulated slippage
    entry_fee: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    risk_amount: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    status: Mapped[PaperTradeStatus] = mapped_column(
        SAEnum(PaperTradeStatus, name="paper_trade_status"), nullable=False, default=PaperTradeStatus.OPEN
    )

    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    proposed_exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # stop or target, whichever hit
    exit_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)      # after simulated slippage
    exit_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "win" | "loss"
    # Idealized, backtest-style R-multiple (-1.0 or +reward_risk, no slippage/fees)
    # alongside the realistic one actually realized after slippage+fees — the gap
    # between the two IS the "naive vs realistic" comparison this milestone exists for.
    r_multiple_ideal: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_multiple_realistic: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_ngn: Mapped[float | None] = mapped_column(Float, nullable=True)

    # The exact plain-language summary shown to the human at approval time —
    # an audit trail of what was actually seen and approved, not just the
    # numbers behind it.
    approval_summary: Mapped[str] = mapped_column(Text, nullable=False)

    signal: Mapped["Signal"] = relationship(back_populates="paper_trade")
    asset: Mapped["Asset"] = relationship()
