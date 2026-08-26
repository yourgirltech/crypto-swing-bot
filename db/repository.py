"""
Thin persistence helpers — map the existing dataclasses/DataFrames (Trade,
TradeProposal, the OHLCV DataFrame from okx_client.py/bybit_client.py) onto
the ORM models in db/models.py. No business logic here, just translation.
"""

from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import (
    Asset, BacktestRun, BacktestTrade, Candle, DerivativesSnapshot, EngineHeartbeat, HumanDecision,
    PaperTrade, PaperTradeStatus, RetryEvent, Signal, SignalStatus,
)
from backtest.backtest_engine import Trade
from proposals.trade_proposal import TradeProposal
from risk.risk_engine import OpenPosition, PortfolioState, RiskVerdict
from strategies.base import ExitResult


def get_or_create_asset(session: Session, symbol: str, exchange: str, category: str) -> Asset:
    asset = session.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None:
        asset = Asset(symbol=symbol, exchange=exchange, category=category)
        session.add(asset)
        session.flush()  # populate asset.id
    return asset


def get_candles(session: Session, asset: Asset, timeframe: str, source: str) -> pd.DataFrame:
    """
    Loads already-persisted candles back into the same DataFrame shape
    OKXClient/BybitClient return (open_time, open, high, low, close,
    volume, turnover), sorted ascending -- i.e. exactly what run_backtest()
    and add_all_indicators() expect. Lets backtesting run entirely off
    Postgres history already saved by a prior live/paper poll or main.py
    run, without depending on the exchange being reachable right now (see
    [[system_health_retry_heartbeat]]/okx_geoblock_workaround memory --
    OKX access from this machine is intermittent).
    """
    rows = session.scalars(
        select(Candle).where(
            Candle.asset_id == asset.id,
            Candle.timeframe == timeframe,
            Candle.source == source,
        ).order_by(Candle.open_time.asc())
    ).all()
    return pd.DataFrame([
        {
            "open_time": r.open_time, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume, "turnover": r.turnover,
        }
        for r in rows
    ])


def save_candles(session: Session, asset: Asset, timeframe: str, source: str, df: pd.DataFrame) -> int:
    """
    Upsert candles for (asset, timeframe, source) — skips rows whose
    open_time is already stored, so re-running a backtest doesn't duplicate
    history. Returns the number of NEW rows inserted.
    """
    existing_times = set(session.scalars(
        select(Candle.open_time).where(
            Candle.asset_id == asset.id,
            Candle.timeframe == timeframe,
            Candle.source == source,
        )
    ).all())

    new_rows = [
        Candle(
            asset_id=asset.id, timeframe=timeframe, source=source,
            open_time=row.open_time.to_pydatetime(),
            open=float(row.open), high=float(row.high), low=float(row.low),
            close=float(row.close), volume=float(row.volume), turnover=float(row.turnover),
        )
        for row in df.itertuples(index=False)
        if row.open_time.to_pydatetime() not in existing_times
    ]
    session.add_all(new_rows)
    return len(new_rows)


def save_backtest_run(session: Session, asset: Asset, timeframe: str, data_source: str,
                       df: pd.DataFrame, params: dict) -> BacktestRun:
    run = BacktestRun(
        asset_id=asset.id, timeframe=timeframe, data_source=data_source,
        date_range_start=df["open_time"].min().to_pydatetime(),
        date_range_end=df["open_time"].max().to_pydatetime(),
        params=params,
    )
    session.add(run)
    session.flush()  # populate run.id
    return run


def _f(x) -> Optional[float]:
    """Coerce numpy.float64 (Trade's price fields come straight from pandas
    bar[...] lookups, never cast to native float) to plain Python float —
    psycopg2 can't adapt numpy scalars in bulk insert mode."""
    return None if x is None else float(x)


def save_backtest_trades(session: Session, run: BacktestRun, trades: List[Trade]) -> int:
    rows = [
        BacktestTrade(
            run_id=run.id,
            entry_time=t.entry_time.to_pydatetime(),
            exit_time=t.exit_time.to_pydatetime() if t.exit_time is not None else None,
            direction=t.direction, entry_price=_f(t.entry_price), stop_price=_f(t.stop_price),
            target_price=_f(t.target_price), exit_price=_f(t.exit_price), outcome=t.outcome,
            r_multiple=_f(t.r_multiple), regime=t.regime,
            rsi_at_entry=_f(t.rsi_at_entry), atr_pct_at_entry=_f(t.atr_pct_at_entry),
            dist_from_ema_fast_pct=_f(t.dist_from_ema_fast_pct),
            dist_from_ema_slow_pct=_f(t.dist_from_ema_slow_pct),
            breakout_margin_pct=_f(t.breakout_margin_pct), bars_since_swing=t.bars_since_swing,
        )
        for t in trades if t.outcome in ("win", "loss")  # only closed trades are meaningful history
    ]
    session.add_all(rows)
    return len(rows)


def save_signal(session: Session, asset: Asset, proposal: TradeProposal, verdict: RiskVerdict,
                 triggering_candle_time) -> Signal:
    """
    verdict is required (not optional/defaulted to PENDING) — every signal
    persisted must have gone through risk.risk_engine.evaluate_trade() first,
    per Milestone 2 ("active gate", not an afterthought a caller can skip).

    triggering_candle_time: the open_time of the candle whose close produced
    this proposal (the last row of the df passed to build_proposal) — lets
    a caller (paper_trading/engine.py) tell "already decided for this
    candle" apart from "a genuinely new candle closed" via
    has_signal_for_candle(), across polls and restarts.
    """
    # TradeProposal's numeric fields can carry numpy.float64 (they trace back
    # to pandas bar[...] lookups via Strategy.compute_stop_loss/compute_take_profit/
    # position_size, same root cause _f() was added for in save_backtest_trades) —
    # coerce to native Python types or psycopg2 fails the same way on insert.
    signal = Signal(
        asset_id=asset.id,
        triggering_candle_time=triggering_candle_time,
        setup_type=proposal.setup_type, direction=proposal.direction,
        entry_price=_f(proposal.entry_price), stop_price=_f(proposal.stop_price),
        target_price=_f(proposal.target_price), risk_amount=_f(proposal.risk_amount),
        position_size=_f(proposal.position_size), reward_risk_ratio=_f(proposal.reward_risk_ratio),
        trend=proposal.trend, regime=proposal.regime, rsi=_f(proposal.rsi),
        backtested_win_rate_pct=_f(proposal.backtested_win_rate_pct),
        backtested_sample_size=int(proposal.backtested_sample_size) if proposal.backtested_sample_size is not None else None,
        backtested_expectancy_r=_f(proposal.backtested_expectancy_r),
        notes=proposal.notes,
        status=SignalStatus.APPROVED if verdict.approved else SignalStatus.REJECTED,
        risk_verdict_reason=verdict.reason,
    )
    session.add(signal)
    session.flush()
    return signal


def has_signal_for_candle(session: Session, asset: Asset, candle_time) -> bool:
    """True if a signal was already generated for this asset off this exact candle."""
    return session.scalar(
        select(Signal.id).where(Signal.asset_id == asset.id, Signal.triggering_candle_time == candle_time)
    ) is not None


def record_human_decision(session: Session, signal: Signal, decision: HumanDecision,
                           reason: Optional[str]) -> Signal:
    """
    Milestone 4: a human's decision on a risk-engine-APPROVED signal. Never
    call this for a REJECTED signal — the whole point of the risk engine
    gate is that a human is never asked to approve something it already
    vetoed (see paper_trading/engine.py).
    """
    signal.human_decision = decision
    signal.human_decision_reason = reason
    signal.human_decision_at = datetime.utcnow()
    session.add(signal)
    session.flush()
    return signal


def create_paper_trade(session: Session, signal: Signal, proposal: TradeProposal,
                        entry_fill_price: float, entry_fee: float, entry_time,
                        approval_summary: str, data_source: str) -> PaperTrade:
    """
    Only ever called after BOTH the risk engine AND a human have approved
    (see Milestone 4). Same numpy.float64 coercion as save_signal — entry_fill_price/
    entry_fee are arithmetic on proposal.entry_price (traces back to pandas), so they
    inherit the same numpy dtype rather than becoming native floats.
    """
    trade = PaperTrade(
        signal_id=signal.id, asset_id=signal.asset_id, data_source=data_source,
        direction=proposal.direction,
        proposed_entry_price=_f(proposal.entry_price), entry_fill_price=_f(entry_fill_price), entry_fee=_f(entry_fee),
        stop_price=_f(proposal.stop_price), target_price=_f(proposal.target_price),
        position_size=_f(proposal.position_size), risk_amount=_f(proposal.risk_amount),
        entry_time=entry_time, status=PaperTradeStatus.OPEN,
        approval_summary=approval_summary,
    )
    session.add(trade)
    session.flush()
    return trade


def get_open_paper_trade(session: Session, asset: Asset) -> Optional[PaperTrade]:
    return session.scalar(
        select(PaperTrade).where(PaperTrade.asset_id == asset.id, PaperTrade.status == PaperTradeStatus.OPEN)
    )


def close_paper_trade(session: Session, trade: PaperTrade, exit_result: ExitResult, exit_fill_price: float,
                       exit_fee: float, exit_time, r_multiple_realistic: float, pnl_ngn: float) -> PaperTrade:
    """Same numpy.float64 coercion as save_signal/create_paper_trade — see their docstrings."""
    trade.status = PaperTradeStatus.CLOSED
    trade.exit_time = exit_time
    trade.proposed_exit_price = _f(exit_result.exit_price)
    trade.exit_fill_price = _f(exit_fill_price)
    trade.exit_fee = _f(exit_fee)
    trade.outcome = exit_result.outcome
    trade.r_multiple_ideal = _f(exit_result.r_multiple)
    trade.r_multiple_realistic = _f(r_multiple_realistic)
    trade.pnl_ngn = _f(pnl_ngn)
    session.add(trade)
    session.flush()
    return trade


def build_portfolio_state(session: Session, account_baseline: float) -> PortfolioState:
    """
    Builds a REAL PortfolioState from actual paper_trades rows — this is
    what resolves risk_engine.py's Milestone 2 "empty PortfolioState"
    limitation for the paper trading path specifically (main.py's one-shot
    backtest demo still uses an at-rest stub; it isn't running a real
    position book).

    account_equity: baseline + all realized pnl_ngn from closed trades.
    peak_equity: the running high-water mark of that same equity curve
    (needed for the risk engine's max-drawdown check).
    daily/weekly_pnl_pct: equity now vs. equity as of the last trade that
    closed at/before 24h/7d ago — exact given equity only changes at
    discrete trade-close events (no live intra-trade P&L is tracked).
    """
    closed = session.scalars(
        select(PaperTrade)
        .where(PaperTrade.status == PaperTradeStatus.CLOSED)
        .order_by(PaperTrade.exit_time)
    ).all()

    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    equity = account_baseline
    peak_equity = account_baseline
    equity_24h_ago = account_baseline
    equity_7d_ago = account_baseline

    for t in closed:
        equity += t.pnl_ngn
        peak_equity = max(peak_equity, equity)
        if t.exit_time <= cutoff_24h:
            equity_24h_ago = equity
        if t.exit_time <= cutoff_7d:
            equity_7d_ago = equity

    daily_pnl_pct = (equity - equity_24h_ago) / equity_24h_ago * 100 if equity_24h_ago else 0.0
    weekly_pnl_pct = (equity - equity_7d_ago) / equity_7d_ago * 100 if equity_7d_ago else 0.0

    open_trades = session.scalars(
        select(PaperTrade).where(PaperTrade.status == PaperTradeStatus.OPEN)
    ).all()
    open_positions = [
        OpenPosition(symbol=t.asset.symbol, direction=t.direction, notional=t.position_size * t.entry_fill_price)
        for t in open_trades
    ]

    return PortfolioState(
        account_equity=equity, peak_equity=peak_equity, open_positions=open_positions,
        daily_pnl_pct=daily_pnl_pct, weekly_pnl_pct=weekly_pnl_pct,
    )


def record_retry_event(session: Session, source: str, request_desc: str, attempt_number: int,
                        max_attempts: int, delay_seconds: float, exception_type: str,
                        exception_message: str) -> RetryEvent:
    """Called from data/okx_client.py's retry loop -- see db/models.py's RetryEvent docstring."""
    event = RetryEvent(
        source=source, request_desc=request_desc, attempt_number=attempt_number,
        max_attempts=max_attempts, delay_seconds=delay_seconds,
        exception_type=exception_type, exception_message=exception_message[:2000],
    )
    session.add(event)
    session.flush()
    return event


def list_recent_retry_events(session: Session, limit: int = 20) -> List[RetryEvent]:
    return list(session.scalars(
        select(RetryEvent).order_by(RetryEvent.occurred_at.desc()).limit(limit)
    ).all())


def count_retry_events_since(session: Session, since: datetime) -> int:
    return session.scalar(
        select(func.count()).select_from(RetryEvent).where(RetryEvent.occurred_at >= since)
    ) or 0


def record_heartbeat(session: Session, engine_name: str, symbol: Optional[str] = None,
                      detail: Optional[str] = None) -> EngineHeartbeat:
    """Called from paper_trading/engine.py's run_once() -- see db/models.py's EngineHeartbeat docstring."""
    hb = EngineHeartbeat(engine_name=engine_name, symbol=symbol, detail=detail)
    session.add(hb)
    session.flush()
    return hb


def get_latest_heartbeat(session: Session, engine_name: str) -> Optional[EngineHeartbeat]:
    return session.scalar(
        select(EngineHeartbeat)
        .where(EngineHeartbeat.engine_name == engine_name)
        .order_by(EngineHeartbeat.checked_in_at.desc())
    )


def record_derivatives_snapshot(session: Session, symbol: str, funding_rate: Optional[float],
                                 open_interest: Optional[float], long_short_ratio: Optional[float],
                                 source: str) -> DerivativesSnapshot:
    """Called from paper_trading/engine.py's run_once() -- see db/models.py's DerivativesSnapshot docstring (Milestone 9, deferred as a live feature -- collection only)."""
    snap = DerivativesSnapshot(
        symbol=symbol, funding_rate=funding_rate, open_interest=open_interest,
        long_short_ratio=long_short_ratio, source=source,
    )
    session.add(snap)
    session.flush()
    return snap


def get_latest_derivatives_snapshot(session: Session, symbol: str) -> Optional[DerivativesSnapshot]:
    """Not consumed by any live code today -- exists for verification/future evidence-gathering only."""
    return session.scalar(
        select(DerivativesSnapshot)
        .where(DerivativesSnapshot.symbol == symbol)
        .order_by(DerivativesSnapshot.captured_at.desc())
    )
