"""
Pullback strategy -- Milestone 7's second new Strategy.

Entry: "buy the dip in an uptrend" (symmetric: "sell the rally in a
downtrend"). Requires an already-established trend per the shared
structure engine (classify_trend says UPTREND/DOWNTREND from the same
swing HH/HL/LH/LL sequencing TrendContinuationBOS uses) -- unlike
Breakout, which fires BEFORE trend structure confirms anything. Within
that trend, the PRIOR bar must have touched or pierced EMA21 (price
pulled back to the trend-following average), and the CURRENT bar must
close back on the trend's side of EMA21 while the prior bar's close was
not (a reclaim on this exact bar, not an already-stale reclaim from
several bars ago).

This is a different entry mechanism from both other strategies built so
far:
- TrendContinuationBOS needs a FRESH break-of-structure print on this bar.
- Breakout needs a fresh range break on this bar.
- Pullback needs neither -- it can fire on any bar, well after the last
  BOS, as long as a pullback-and-reclaim of EMA21 just happened. It does
  not use the swing/BOS signal at all (only trend_state), same
  "ignore what this strategy doesn't need" pattern as Breakout ignoring
  swings/signal.

Confirmation: only trades within the three genuinely trending regimes
(strong_bull_trend, weak_bull_trend, strong_bear_trend) -- sideways,
hyperbolic, and panic_recovery are excluded, since "buy the pullback"
presumes a trend worth continuing, which is exactly what those three
regimes don't establish per regime/regime_classifier.py.

Invalidation: none defined, same as the other two strategies -- the
entry triggers immediately on the reclaim bar itself.

Stop-loss: ATR-multiple beyond entry (default 1.5x ATR14, same as
TrendContinuationBOS -- a pullback entry is anchored close to the trend's
own EMA, so a tighter stop than Breakout's 2.0x is appropriate here).
Take-profit: fixed reward:risk multiple beyond the stop (default 2.0R).
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: not hard-excluded at market_regime_requirements()
level (kept as a confirm_entry-level filter, same architectural choice
as the other two strategies, so the regime rule lives with the strategy
that depends on it rather than the caller).

VALIDATION STATUS: NOT VALIDATED -- do not treat this as a live/trusted
setup. Run via backtest/validate_milestone7.py (BTCUSDT, 5yr 4H persisted
history, 2026-08-26):

Full period: 38 trades, 31.6% win rate, expectancy -0.053R -- already net
negative before any held-out split.
In-sample (everything before the most recent 365 days): 31 trades, 32.3%
win rate, expectancy -0.032R.
Held-out (most recent 365 days, genuine out-of-sample, NOT used to design
this strategy): 7 trades, 28.6% win rate, expectancy -0.143R.

Unlike Breakout (which looked profitable in-sample and only failed on the
held-out slice -- a sign flip), Pullback is consistently negative across
ALL three slices -- full period, in-sample, and held-out. This is a
DIFFERENT kind of failure than Breakout's: Breakout's in-sample edge
didn't generalize forward (overfitting to the years backtested); Pullback
never had an edge to begin with, in-sample OR held-out, which points at
the entry logic itself lacking edge here rather than a generalization
failure. Held-out sample is very small (7 trades, below this file's own
reliability bar) so don't read too much into -0.143R specifically, but
the direction agrees with both larger slices, so this isn't just
small-sample noise flipping a sign.

CONFIDENCE CAVEAT: the full-period sample itself is small (38 trades
total, vs. Breakout's 126) -- roughly a third the evidence. The
"lacks edge" conclusion above is directionally consistent across all
three slices, which is meaningful, but with this few total trades treat
it as a reasonable working conclusion, not a statistically strong one --
a genuinely different pullback definition could still turn up an edge
this sample is simply too small to rule out.

Regime breakdown: 32 of 38 trades landed in weak_bull_trend (-0.062R,
the dominant and clearly negative bucket); strong_bull_trend (3 trades,
+1.000R) and strong_bear_trend (3 trades, -1.000R) are each too small
individually to draw a conclusion from.

Kept in the codebase (not deleted) as a base for future iteration, same
"pause, don't delete" precedent as ETH/Breakout. Candidate revision
directions: the EMA21-touch-and-reclaim condition may be firing on noise
within a choppy weak_bull_trend rather than a genuine pullback (an ATR-
scaled minimum pullback depth, rather than "any touch," might filter
this out); or the reclaim itself may need multi-bar confirmation instead
of a single-bar cross, since a single-bar EMA reclaim in a weak trend is
a fairly weak signal on its own.
"""

from typing import Optional, Set

import pandas as pd

from strategies.base import EntrySetup, ExitResult, Strategy
from structure.market_structure import TrendState


class Pullback(Strategy):
    name = "pullback"

    def __init__(self, atr_stop_mult: float = 1.5, reward_risk: float = 2.0,
                 rsi_extreme: tuple = (25, 75)):
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.rsi_extreme = rsi_extreme
        # See Breakout.swing_lookback -- every Strategy is expected to
        # expose this for run_backtest()'s SwingTracker construction, even
        # though this strategy's own entry logic doesn't use swings.
        self.swing_lookback = 5

    def market_regime_requirements(self) -> Optional[Set[str]]:
        return None  # regime gating lives in confirm_entry -- see module docstring

    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        if len(window) < 2:
            return None

        bar = window.iloc[-1]
        prev = window.iloc[-2]
        atr_val = bar["atr"]
        if pd.isna(atr_val) or pd.isna(prev["ema_21"]):
            return None

        ema_fast = bar["ema_21"]
        prev_ema_fast = prev["ema_21"]
        close = float(bar["close"])
        rsi_val = bar["rsi"]

        if trend_state == TrendState.UPTREND:
            touched_ema = prev["low"] <= prev_ema_fast
            reclaimed = close > ema_fast and prev["close"] <= prev_ema_fast
            if touched_ema and reclaimed and rsi_val < self.rsi_extreme[1]:
                direction = "long"
            else:
                return None
        elif trend_state == TrendState.DOWNTREND:
            touched_ema = prev["high"] >= prev_ema_fast
            reclaimed = close < ema_fast and prev["close"] >= prev_ema_fast
            if touched_ema and reclaimed and rsi_val > self.rsi_extreme[0]:
                direction = "short"
            else:
                return None
        else:
            return None

        diagnostics = {
            "rsi_at_entry": float(rsi_val),
            "atr_pct_at_entry": float(atr_val / close * 100),
            "dist_from_ema_fast_pct": float((close - ema_fast) / ema_fast * 100),
            "dist_from_ema_slow_pct": float((close - bar["ema_50"]) / bar["ema_50"] * 100),
            "breakout_margin_pct": None,  # not a breakout/swing-based setup -- see module docstring
            "bars_since_swing": None,
        }
        return EntrySetup(direction=direction, entry_price=close, diagnostics=diagnostics)

    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        return regime in ("strong_bull_trend", "weak_bull_trend", "strong_bear_trend")

    def check_invalidation(self, setup: EntrySetup, window: pd.DataFrame) -> bool:
        return False  # see module docstring -- no pending-setup window exists in this strategy

    def compute_stop_loss(self, setup: EntrySetup, window: pd.DataFrame) -> float:
        atr_val = window.iloc[-1]["atr"]
        if setup.direction == "long":
            return setup.entry_price - atr_val * self.atr_stop_mult
        return setup.entry_price + atr_val * self.atr_stop_mult

    def compute_take_profit(self, setup: EntrySetup, stop_price: float) -> float:
        risk_dist = abs(setup.entry_price - stop_price)
        if setup.direction == "long":
            return setup.entry_price + risk_dist * self.reward_risk
        return setup.entry_price - risk_dist * self.reward_risk

    def position_size(self, risk_amount: float, entry_price: float, stop_price: float) -> float:
        risk_dist = abs(entry_price - stop_price)
        return risk_amount / risk_dist if risk_dist else 0.0

    def check_exit(self, direction: str, stop_price: float, target_price: float,
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
