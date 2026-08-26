"""
Backtest engine.

Strategy-agnostic as of Milestone 3: run_backtest() takes a
strategies.base.Strategy instance and delegates every trading decision
(entry, confirmation, invalidation, stop-loss, take-profit, position
sizing, exit) to it. This module owns only the walk-forward mechanics --
building a no-lookahead window at each bar, running the shared structure/
regime engines, tracking the currently-open trade, and turning closed
trades into Trade/BacktestResult records for reporting and persistence.

This produces REAL numbers (win rate, avg win/loss, expectancy, max
drawdown) from historical data — not invented probabilities. Those
numbers are what feed the "chance of profit" figure in trade proposals.
"""

from dataclasses import dataclass, field
from typing import List
import pandas as pd
import numpy as np

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structure.market_structure import (
    SwingTracker, label_swing_sequence, classify_trend, detect_bos_choch,
)
from indicators.indicators import add_all_indicators
from regime.regime_classifier import classify_regime
from strategies.base import Strategy
from risk.position_sizing import PortfolioState, size_position
from config.config import RiskConfig


@dataclass
class Trade:
    entry_index: int
    entry_time: pd.Timestamp
    direction: str          # "long" | "short"
    entry_price: float
    stop_price: float
    target_price: float
    regime: str = None      # regime classification at entry (see regime/regime_classifier.py)
    # Entry-time diagnostics, captured for post-hoc "what distinguishes winners
    # from losers" analysis (e.g. within a specific regime) — also fed into
    # Strategy.confirm_entry() as `diagnostics` (see strategies/base.py).
    rsi_at_entry: float = None
    atr_pct_at_entry: float = None       # ATR as % of entry price (volatility relative to price)
    dist_from_ema_fast_pct: float = None  # (entry - ema_21) / ema_21 * 100
    dist_from_ema_slow_pct: float = None  # (entry - ema_50) / ema_50 * 100
    breakout_margin_pct: float = None    # how far entry price cleared the swing that triggered the BOS
    bars_since_swing: int = None         # bars between the triggering swing and entry
    # Position sizing (Milestone 4 calibration fix, 2026-08-25): position_size
    # is the ACTUAL size taken -- risk.position_sizing.size_position() clamps
    # it to whichever of the position/portfolio/correlated caps leaves the
    # least room, if any is tighter than the risk-based size, so risk_amount
    # here is the REAL $ at risk, which may be LESS than balance *
    # risk_per_trade_pct/100 (never more). was_capped/binding_constraint
    # record whether/which cap actually bound, for auditing how often each
    # backstop engages (see BacktestResult.sizing_summary()).
    position_size: float = None
    risk_amount: float = None
    was_capped: bool = None
    binding_constraint: str = None
    exit_index: int = None
    exit_time: pd.Timestamp = None
    exit_price: float = None
    outcome: str = None     # "win" | "loss" | "open"
    r_multiple: float = None


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.outcome in ("win", "loss")]
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.outcome == "win")
        return round(wins / len(closed) * 100, 1)

    @property
    def avg_win_r(self) -> float:
        wins = [t.r_multiple for t in self.trades if t.outcome == "win"]
        return round(np.mean(wins), 2) if wins else 0.0

    @property
    def avg_loss_r(self) -> float:
        losses = [t.r_multiple for t in self.trades if t.outcome == "loss"]
        return round(np.mean(losses), 2) if losses else 0.0

    @property
    def expectancy_r(self) -> float:
        closed = [t.r_multiple for t in self.trades if t.outcome in ("win", "loss")]
        return round(np.mean(closed), 3) if closed else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        curve = np.array(self.equity_curve)
        peak = np.maximum.accumulate(curve)
        drawdown = (curve - peak) / peak * 100
        return round(drawdown.min(), 2)

    def summary(self) -> dict:
        closed = [t for t in self.trades if t.outcome in ("win", "loss")]
        return {
            "total_trades": len(closed),
            "win_rate_pct": self.win_rate,
            "avg_win_r": self.avg_win_r,
            "avg_loss_r": self.avg_loss_r,
            "expectancy_r": self.expectancy_r,
            "max_drawdown_pct": self.max_drawdown_pct,
        }

    def sizing_summary(self) -> dict:
        """
        How often the notional-position-size cap actually bound (Milestone 4
        calibration fix), and what effective risk % resulted on those capped
        trades vs. the uncapped ones. Uses each trade's entry-time balance
        (risk_amount / effective_risk_pct's implied balance) — since
        risk_amount is already the actual $ at risk, effective_risk_pct here
        is computed relative to the trade's OWN risk_amount basis, not a
        fixed global balance.
        """
        closed = [t for t in self.trades if t.outcome in ("win", "loss")]
        capped = [t for t in closed if t.was_capped]
        uncapped = [t for t in closed if not t.was_capped]
        by_constraint: dict = {}
        for t in capped:
            by_constraint[t.binding_constraint] = by_constraint.get(t.binding_constraint, 0) + 1
        return {
            "total_trades": len(closed),
            "capped_trades": len(capped),
            "uncapped_trades": len(uncapped),
            "capped_pct": round(len(capped) / len(closed) * 100, 1) if closed else 0.0,
            "capped_by_constraint": by_constraint,
        }

    def by_regime(self) -> dict:
        """
        Breaks closed trades down by the regime classification at entry.
        Returns {regime_name: {"trades": int, "win_rate_pct": float, "expectancy_r": float}}.
        """
        closed = [t for t in self.trades if t.outcome in ("win", "loss")]
        grouped: dict = {}
        for t in closed:
            grouped.setdefault(t.regime or "unknown", []).append(t)

        breakdown = {}
        for regime, trades in grouped.items():
            wins = sum(1 for t in trades if t.outcome == "win")
            breakdown[regime] = {
                "trades": len(trades),
                "win_rate_pct": round(wins / len(trades) * 100, 1),
                "expectancy_r": round(float(np.mean([t.r_multiple for t in trades])), 3),
            }
        return breakdown


def run_backtest(df: pd.DataFrame, strategy: Strategy, risk_config: RiskConfig, symbol: str,
                  starting_balance: float = 1_000_000.0) -> BacktestResult:
    """
    Walk-forward simulation: at each bar, re-run structure analysis on data
    up to that point only (no look-ahead), ask `strategy` whether an entry,
    confirmation, and non-invalidation all hold, and if so simulate the
    trade using the strategy's own stop/target/exit rules and risk_config-
    governed sizing until it closes.

    risk_config is required (no default, replacing separate risk_per_trade_pct/
    max_position_size_pct params) -- risk.position_sizing.size_position()
    sizes each trade to risk_config.risk_per_trade_pct UNLESS max_position_size_pct/
    max_portfolio_exposure_pct/max_correlated_exposure_pct would be tighter, in
    which case it sizes DOWN (never rejected, never sized up). This is the
    SAME sizing call the live proposal path (build_proposal()) makes, so
    backtested expectancy reflects the sizing that will actually be used --
    not an idealized always-full-risk assumption. Since run_backtest() only
    ever tracks one open position for one symbol at a time, the portfolio/
    correlated caps see an empty PortfolioState (no other positions to sum
    against) -- they reduce to their full percentage of equity each time,
    same as they would live for a single open BTC position with ETH paused.
    """
    df = add_all_indicators(df, ema_fast=21, ema_slow=50, rsi_period=14, atr_period=14)
    result = BacktestResult()
    balance = starting_balance
    in_trade = False
    open_trade: Trade = None

    min_bars = 60  # warmup for indicators + structure
    tracker = SwingTracker(lookback=strategy.swing_lookback)

    for i in range(min_bars, len(df)):
        bar = df.iloc[i]

        if in_trade:
            exit_result = strategy.check_exit(
                open_trade.direction, open_trade.entry_price, open_trade.stop_price, open_trade.target_price, bar
            )
            if exit_result is not None:
                open_trade.exit_index = i
                open_trade.exit_time = bar["open_time"]
                open_trade.exit_price = exit_result.exit_price
                open_trade.outcome = exit_result.outcome
                open_trade.r_multiple = exit_result.r_multiple
                # Use the ACTUAL risk_amount computed at entry (already
                # notional-capped if it applied) -- not a fresh balance*pct
                # recompute, which would silently re-apply full target risk.
                balance += open_trade.risk_amount * open_trade.r_multiple
                result.trades.append(open_trade)
                result.equity_curve.append(balance)
                in_trade = False
                open_trade = None
            continue

        window = df.iloc[:i + 1]
        swings = tracker.update(window)
        swings = label_swing_sequence(swings)
        trend_state = classify_trend(swings)
        signal = detect_bos_choch(swings, trend_state)

        setup = strategy.check_entry(window, swings, trend_state, signal)
        if setup is None:
            continue

        regime_info = classify_regime(window, ema_fast_col="ema_21", ema_slow_col="ema_50")
        if not strategy.confirm_entry(regime_info["regime"], setup.diagnostics):
            continue
        if strategy.check_invalidation(setup, window):
            continue

        stop = strategy.compute_stop_loss(setup, window)
        target = strategy.compute_take_profit(setup, stop, window)

        risk_amount_target = balance * (risk_config.risk_per_trade_pct / 100)
        raw_size = strategy.position_size(risk_amount_target, setup.entry_price, stop)
        # No other position is ever open concurrently in this single-symbol,
        # single-position backtest -- portfolio/correlated caps see an empty
        # book and reduce to their full percentage of equity (see docstring).
        empty_portfolio = PortfolioState(account_equity=balance, peak_equity=balance, open_positions=[])
        sizing = size_position(
            raw_size, setup.entry_price, stop, symbol, empty_portfolio,
            risk_config.max_position_size_pct, risk_config.max_portfolio_exposure_pct,
            risk_config.max_correlated_exposure_pct, risk_config.correlated_groups,
        )

        open_trade = Trade(entry_index=i, entry_time=bar["open_time"], direction=setup.direction,
                            entry_price=setup.entry_price, stop_price=stop, target_price=target,
                            regime=regime_info["regime"],
                            position_size=sizing.position_size, risk_amount=sizing.risk_amount,
                            was_capped=sizing.was_capped, binding_constraint=sizing.binding_constraint,
                            **setup.diagnostics)
        in_trade = True

    return result
