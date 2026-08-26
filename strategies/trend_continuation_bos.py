"""
Trend-continuation BOS strategy -- Milestone 3's first formalized Strategy.

Formalizes the setup that used to live directly inside
backtest_engine.run_backtest() and, separately, was duplicated (with a
"kept consistent so these don't drift" comment as the only safeguard)
inside proposals/trade_proposal.py's build_proposal(). Both now call this
one class through the Strategy interface (strategies/base.py).

Entry: BOS confirms trend continuation AND the EMA21/EMA50 cross agrees
with that trend AND RSI is not in an extreme (avoids buying blow-off tops
/ selling panic bottoms).

Confirmation: in the `weak_bull_trend` regime only, additionally require
price to actually be trading above EMA21 at entry, not just that the
EMA21>EMA50 cross holds. This used to be a bolt-on `entry_filter`
parameter to a generic engine (backtest_engine.weak_bull_trend_ema_filter)
-- it's now part of this strategy's own confirm_entry(), which is what
Milestone 3 asked for. Full validation history, unchanged from that prior
version:

Origin (BTCUSDT, 5yr 4H OKX data, 2026-08-24 review): weak_bull_trend was
the most common regime (78/149 trades) and the one dragging overall
expectancy down (-0.038R). Within it, winning trades entered with price
meaningfully above EMA21 (+0.47% avg) while losing trades entered at/below
it (-0.11% avg). Applying this filter only to weak_bull_trend: full 5yr
sample 78->55 trades, win rate 32.1%->36.4%, expectancy -0.038R->+0.091R.

Held-out validation (most recent 1yr, NOT used to pick this filter): the
improvement direction held (win rate and expectancy both improved, in
every slice checked) but was more modest than the full-period number
suggested -- weak_bull_trend stayed net-negative on held-out data even
with the filter (-0.143R -> -0.100R, 14->10 trades); it did not flip to
profitable out-of-sample. The filter reduces the damage in this regime;
it does not cure it. Held-out sample sizes are small (10-14 trades), so
treat the exact magnitude as directional, not precise -- a live area for
further iteration, not a closed case.

Invalidation: none defined. This strategy's entries trigger immediately
on the same bar the structural condition is met -- there is no pending,
multi-bar setup window to invalidate before a fill. check_invalidation()
always returns False; it's a real hook on the interface for a future
multi-bar variant (or a different strategy) to actually use, not invented
behavior standing in for something that doesn't exist today.

Stop-loss: ATR-multiple beyond entry (default 1.5x ATR14).
Take-profit: fixed reward:risk multiple beyond the stop (default 2.0R).
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: none hard-excluded at this level -- see
market_regime_requirements().
"""

from typing import Optional, Set

import pandas as pd

from strategies.base import EntrySetup, ExitResult, Strategy
from structure.market_structure import TrendState


class TrendContinuationBOS(Strategy):
    name = "trend_continuation_bos"

    def __init__(self, atr_stop_mult: float = 1.5, reward_risk: float = 2.0,
                 swing_lookback: int = 5, rsi_extreme: tuple = (25, 75)):
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.swing_lookback = swing_lookback
        self.rsi_extreme = rsi_extreme

    def market_regime_requirements(self) -> Optional[Set[str]]:
        return None  # not hard-gated by regime here -- see confirm_entry's weak_bull_trend rule

    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        bar = window.iloc[-1]
        rsi_val = bar["rsi"]
        atr_val = bar["atr"]

        if signal != "BOS" or pd.isna(atr_val):
            return None

        if trend_state == TrendState.UPTREND and bar["trend_filter"] == "bullish" and rsi_val < self.rsi_extreme[1]:
            direction = "long"
        elif trend_state == TrendState.DOWNTREND and bar["trend_filter"] == "bearish" and rsi_val > self.rsi_extreme[0]:
            direction = "short"
        else:
            return None

        labeled = [s for s in swings if s.label is not None]
        triggering_swing = labeled[-1] if labeled else None
        entry_price = float(bar["close"])
        diagnostics = _entry_diagnostics(
            entry_price, atr_val, rsi_val, bar, triggering_swing, len(window) - 1, direction
        )
        return EntrySetup(direction=direction, entry_price=entry_price, diagnostics=diagnostics)

    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        if regime != "weak_bull_trend":
            return True
        return diagnostics["dist_from_ema_fast_pct"] is not None and diagnostics["dist_from_ema_fast_pct"] > 0

    def check_invalidation(self, setup: EntrySetup, window: pd.DataFrame) -> bool:
        return False  # see module docstring -- no pending-setup window exists in this strategy

    def compute_stop_loss(self, setup: EntrySetup, window: pd.DataFrame) -> float:
        atr_val = window.iloc[-1]["atr"]
        if setup.direction == "long":
            return setup.entry_price - atr_val * self.atr_stop_mult
        return setup.entry_price + atr_val * self.atr_stop_mult

    def compute_take_profit(self, setup: EntrySetup, stop_price: float, window: pd.DataFrame) -> float:
        risk_dist = abs(setup.entry_price - stop_price)
        if setup.direction == "long":
            return setup.entry_price + risk_dist * self.reward_risk
        return setup.entry_price - risk_dist * self.reward_risk

    def position_size(self, risk_amount: float, entry_price: float, stop_price: float) -> float:
        risk_dist = abs(entry_price - stop_price)
        return risk_amount / risk_dist if risk_dist else 0.0

    def check_exit(self, direction: str, entry_price: float, stop_price: float, target_price: float,
                    bar: pd.Series) -> Optional[ExitResult]:
        if direction == "long":
            if bar["low"] <= stop_price:
                return ExitResult("loss", stop_price, -1.0)
            if bar["high"] >= target_price:
                return ExitResult("win", target_price, self.reward_risk)
        else:
            if bar["high"] >= stop_price:
                return ExitResult("loss", stop_price, -1.0)
            if bar["low"] <= target_price:
                return ExitResult("win", target_price, self.reward_risk)
        return None


def _entry_diagnostics(entry: float, atr_val: float, rsi_val: float, bar, triggering_swing,
                        i: int, direction: str) -> dict:
    """Entry-time diagnostics for post-hoc winner-vs-loser analysis (see backtest_engine.Trade fields)."""
    if triggering_swing is not None:
        if direction == "long":
            breakout_margin_pct = (entry - triggering_swing.price) / triggering_swing.price * 100
        else:
            breakout_margin_pct = (triggering_swing.price - entry) / triggering_swing.price * 100
        bars_since_swing = i - triggering_swing.index
    else:
        breakout_margin_pct = None
        bars_since_swing = None

    return {
        "rsi_at_entry": float(rsi_val),
        "atr_pct_at_entry": float(atr_val / entry * 100),
        "dist_from_ema_fast_pct": float((entry - bar["ema_21"]) / bar["ema_21"] * 100),
        "dist_from_ema_slow_pct": float((entry - bar["ema_50"]) / bar["ema_50"] * 100),
        "breakout_margin_pct": breakout_margin_pct,
        "bars_since_swing": bars_since_swing,
    }
