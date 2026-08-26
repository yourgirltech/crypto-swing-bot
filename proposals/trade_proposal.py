"""
Trade proposal builder.

Combines: current structure state, regime, indicator readings, and
backtested stats for the matched setup type into ONE object.

This is deliberately NOT where "chance of profit" gets invented — that
number comes only from backtest.summary()['win_rate_pct'] for the setup
type that matches. If we haven't backtested a setup type, this returns
None for win-rate rather than guessing.

As of Milestone 3, entry/confirmation/invalidation/stop/target/sizing are
delegated to a strategies.base.Strategy instance, the SAME kind of object
backtest_engine.run_backtest() runs -- so a live proposal and the
backtested stats shown alongside it are guaranteed to come from the exact
same rules, not two hand-synced copies of the same logic.

The LLM synthesis layer (Phase 2) turns this object into a readable
narrative. This module only produces the numbers.
"""

from dataclasses import dataclass, asdict
from typing import Optional
import pandas as pd

from structure.market_structure import find_swings, label_swing_sequence, classify_trend, detect_bos_choch
from indicators.indicators import add_all_indicators
from regime.regime_classifier import classify_regime
from strategies.base import Strategy
from risk.position_sizing import PortfolioState, size_position
from config.config import RiskConfig


@dataclass
class TradeProposal:
    symbol: str
    setup_type: str
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_amount: float
    position_size: float
    reward_risk_ratio: float
    trend: str
    regime: str
    rsi: float
    backtested_win_rate_pct: Optional[float]
    backtested_sample_size: Optional[int]
    backtested_expectancy_r: Optional[float]
    notes: str

    def as_dict(self) -> dict:
        return asdict(self)


def build_proposal(df: pd.DataFrame, symbol: str, strategy: Strategy,
                    risk_config: RiskConfig, portfolio: PortfolioState,
                    backtest_summary: Optional[dict] = None) -> Optional[TradeProposal]:
    """
    Looks at the LATEST bar of df and, if `strategy` finds (and confirms,
    and doesn't invalidate) a valid setup, returns a TradeProposal. Returns
    None if no setup is present right now — the bot should not force a
    trade to exist.

    risk_config + portfolio (replacing the previous bare account_balance/
    risk_per_trade_pct/max_position_size_pct floats) are required so sizing
    can apply risk.position_sizing.size_position()'s full position/
    portfolio/correlated-exposure clamp -- account_balance is now always
    portfolio.account_equity, the single source of truth also used by
    risk.risk_engine.evaluate_trade() on this same proposal afterward.
    """
    df = add_all_indicators(df, ema_fast=21, ema_slow=50, rsi_period=14, atr_period=14)

    swings = find_swings(df, lookback=strategy.swing_lookback)
    swings = label_swing_sequence(swings)
    trend_state = classify_trend(swings)
    signal = detect_bos_choch(swings, trend_state)

    setup = strategy.check_entry(df, swings, trend_state, signal)
    if setup is None:
        return None

    regime_info = classify_regime(df, ema_fast_col="ema_21", ema_slow_col="ema_50")
    if not strategy.confirm_entry(regime_info["regime"], setup.diagnostics):
        return None
    if strategy.check_invalidation(setup, df):
        return None

    stop = strategy.compute_stop_loss(setup, df)
    target = strategy.compute_take_profit(setup, stop)

    account_balance = portfolio.account_equity
    risk_amount_target = account_balance * (risk_config.risk_per_trade_pct / 100)
    raw_size = strategy.position_size(risk_amount_target, setup.entry_price, stop)
    sizing = size_position(
        raw_size, setup.entry_price, stop, symbol, portfolio,
        risk_config.max_position_size_pct, risk_config.max_portfolio_exposure_pct,
        risk_config.max_correlated_exposure_pct, risk_config.correlated_groups,
    )
    position_size = sizing.position_size
    risk_amount = sizing.risk_amount

    risk_dist = abs(setup.entry_price - stop)
    reward_dist = abs(target - setup.entry_price)
    reward_risk_ratio = round(reward_dist / risk_dist, 2) if risk_dist else 0.0

    win_rate = backtest_summary.get("win_rate_pct") if backtest_summary else None
    sample_size = backtest_summary.get("total_trades") if backtest_summary else None
    expectancy = backtest_summary.get("expectancy_r") if backtest_summary else None

    rsi_val = df.iloc[-1]["rsi"]
    notes = (
        f"Setup: {strategy.name} in {trend_state.value}, regime={regime_info['regime']}. "
        f"RSI={rsi_val:.1f}. "
        + (f"Backtested on {sample_size} historical trades of this setup type."
           if sample_size else
           "No backtest run yet for this setup type — win rate below is unknown, not assumed.")
    )
    if sizing.was_capped:
        actual_risk_pct = risk_amount / account_balance * 100 if account_balance else 0.0
        constraint_label = {
            "position_cap": "max position size",
            "portfolio_cap": "max portfolio exposure",
            "correlated_cap": "max correlated exposure",
        }.get(sizing.binding_constraint, sizing.binding_constraint)
        notes += (
            f" NOTE: position size was reduced by the {constraint_label} safety cap "
            f"(risk_per_trade_pct target was {risk_config.risk_per_trade_pct:.2f}%; actual risk on "
            f"this trade is {actual_risk_pct:.2f}%, not the full target)."
        )

    return TradeProposal(
        symbol=symbol,
        setup_type=strategy.name,
        direction=setup.direction,
        entry_price=round(setup.entry_price, 2),
        stop_price=round(stop, 2),
        target_price=round(target, 2),
        risk_amount=round(risk_amount, 2),
        position_size=round(position_size, 6),
        reward_risk_ratio=reward_risk_ratio,
        trend=trend_state.value,
        regime=regime_info["regime"],
        rsi=round(float(rsi_val), 1),
        backtested_win_rate_pct=win_rate,
        backtested_sample_size=sample_size,
        backtested_expectancy_r=expectancy,
        notes=notes,
    )
