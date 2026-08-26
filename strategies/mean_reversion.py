"""
Mean-reversion strategy -- Milestone 7's third new Strategy.

Entry: current bar's close at or beyond a Bollinger Band extreme (close
<= bb_lower for long, close >= bb_upper for short -- see
indicators/indicators.py's bollinger_bands, already computed on every
window this strategy sees) AND RSI confirms the same extreme (RSI < 30
for long, RSI > 70 for short) -- a purely statistical "price and momentum
are both stretched" definition, not structure/swing-based like the other
three strategies built so far.

Confirmation: hard-gated to the `sideways` regime ONLY (regime/
regime_classifier.py's SIDEWAYS label) -- mean reversion is explicitly
the wrong idea to trade against a real trend (fading a strong_bull_trend
move because RSI/BB say "overbought" is exactly how a trend-following
account bleeds out), so every other regime is rejected outright.

Invalidation: none defined, same as the other three strategies -- the
entry triggers immediately on the extreme bar itself.

Stop-loss: ATR-multiple beyond entry (default 1.5x ATR14, same as
TrendContinuationBOS/Pullback -- a BB-extreme entry is already a stretched
price, so a moderate stop is appropriate; wider than that risks holding
through a genuine breakout rather than a reversion).
Take-profit: targets the Bollinger Band midline (bb_mid) -- the actual
reversion this strategy is betting on -- falling back to the fixed 2.0R
target (the same one every other strategy here uses) only when bb_mid
isn't a genuine, sane target for this trade: either it's on the wrong
side of entry (the band shifted since the trade was taken) or it sits
closer to entry than the stop distance (a sub-1:1 reward:risk floor,
regardless of win rate). See compute_take_profit()'s own docstring for
the exact logic. This was originally a fixed 2.0R target, same as every
other strategy here, until the Strategy ABC's compute_take_profit() was
widened to receive the live window (not just entry/stop prices) --
see docs/ARCHITECTURE.md's Milestone 7 cross-cutting note on why the
original fixed target was flagged as a likely poor fit for this
strategy's trade shape specifically.
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: enforced in confirm_entry rather than
market_regime_requirements() for consistency with the other three
strategies -- see their docstrings for why that architectural choice was
made across the board.

VALIDATION STATUS: NOT VALIDATED -- do not treat this as a live/trusted
setup. Two backtests exist for this strategy; both fail. Run via
backtest/validate_milestone7.py (BTCUSDT, 5yr 4H persisted history):

**Original run (2026-08-26, fixed 2.0R target -- the same one every
other strategy here used):** full period 132 trades, -0.114R. In-sample
103 trades, -0.068R. Held-out (365d) 29 trades, -0.276R.

**Re-test after compute_take_profit() was widened to target bb_mid, with
a fixed-2.0R fallback when bb_mid sits on the wrong side of entry or
closer than the stop distance (2026-08-26, same session, same 132
trades -- targeting a different price doesn't change which bars trigger
an entry):**

Full period: 132 trades, 30.3% win rate, avg win 2.07R, expectancy
-0.068R (up from -0.114R).
In-sample: 103 trades, 32.0% win rate, avg win 2.09R, expectancy -0.011R
(up from -0.068R -- nearly break-even).
Held-out: 29 trades, 24.1% win rate, avg win 2.02R, expectancy **-0.27R**
(essentially unchanged from -0.276R).

avg_win_r barely moved from 2.0 (2.02-2.09R across slices), meaning the
bb_mid target was usually FARTHER from entry than the old fixed 2R, not
closer -- a band-touching entry sits ~2 standard deviations from bb_mid
by construction, which is typically a wider move than 2x the ATR-based
stop distance. The fallback-to-fixed-2R path was rarely needed.

**Conclusion: the exit-logic mismatch was a real, measurable confound
(in-sample expectancy improved by 0.057R, full-period by 0.046R), but
fixing it did NOT validate the strategy.** Held-out expectancy is
unchanged in every way that matters (-0.27R vs -0.276R) -- this
strategy's failure was never primarily about the fixed 2R target being a
poor fit; the BB-extreme + RSI-extreme entry condition itself, even
restricted to the `sideways` regime it was designed for and even given a
target shaped for its own trade type, does not show a genuine
out-of-sample edge on BTC 4H. A confound was correctly identified and
removed (per docs/ARCHITECTURE.md's Milestone 7 cross-cutting note), and
removing it changed the in-sample story but not the held-out one --
exactly the kind of result held-out validation exists to catch: an
in-sample-only improvement that doesn't survive contact with unseen data.

The confirm_entry regime gate is still doing exactly what it was built
to do (100% of trades land in `sideways`), so this remains a genuine
"the entry condition itself lacks an edge in its own target regime"
result, not a mis-gated or now-outdated-exit conclusion.

Kept in the codebase (not deleted), same "pause, don't delete" precedent
as Breakout/Pullback/RangeTrading. Not registered in
strategies/registry.py or exposed on the frontend Strategies page while
unvalidated.
"""

from typing import Optional, Set

import pandas as pd

from strategies.base import EntrySetup, ExitResult, Strategy
from structure.market_structure import TrendState


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(self, atr_stop_mult: float = 1.5, reward_risk: float = 2.0,
                 rsi_oversold: float = 30.0, rsi_overbought: float = 70.0):
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        # See Breakout.swing_lookback -- every Strategy is expected to
        # expose this for run_backtest()'s SwingTracker construction, even
        # though this strategy's own entry logic doesn't use swings.
        self.swing_lookback = 5

    def market_regime_requirements(self) -> Optional[Set[str]]:
        return None  # regime gating lives in confirm_entry -- see module docstring

    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        bar = window.iloc[-1]
        atr_val = bar["atr"]
        bb_lower, bb_upper = bar["bb_lower"], bar["bb_upper"]
        if pd.isna(atr_val) or pd.isna(bb_lower) or pd.isna(bb_upper):
            return None

        close = float(bar["close"])
        rsi_val = bar["rsi"]

        if close <= bb_lower and rsi_val < self.rsi_oversold:
            direction = "long"
        elif close >= bb_upper and rsi_val > self.rsi_overbought:
            direction = "short"
        else:
            return None

        diagnostics = {
            "rsi_at_entry": float(rsi_val),
            "atr_pct_at_entry": float(atr_val / close * 100),
            "dist_from_ema_fast_pct": float((close - bar["ema_21"]) / bar["ema_21"] * 100),
            "dist_from_ema_slow_pct": float((close - bar["ema_50"]) / bar["ema_50"] * 100),
            "breakout_margin_pct": None,  # not a breakout/swing-based setup -- see module docstring
            "bars_since_swing": None,
        }
        return EntrySetup(direction=direction, entry_price=close, diagnostics=diagnostics)

    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        return regime == "sideways"

    def check_invalidation(self, setup: EntrySetup, window: pd.DataFrame) -> bool:
        return False  # see module docstring -- no pending-setup window exists in this strategy

    def compute_stop_loss(self, setup: EntrySetup, window: pd.DataFrame) -> float:
        atr_val = window.iloc[-1]["atr"]
        if setup.direction == "long":
            return setup.entry_price - atr_val * self.atr_stop_mult
        return setup.entry_price + atr_val * self.atr_stop_mult

    def compute_take_profit(self, setup: EntrySetup, stop_price: float, window: pd.DataFrame) -> float:
        """
        Targets the Bollinger Band midline (bb_mid) -- the actual "reversion"
        this strategy is betting on, rather than a fixed reward:risk
        multiple borrowed from a trend-continuation strategy (see this
        file's VALIDATION STATUS docstring). Falls back to the fixed
        reward_risk target when bb_mid isn't a genuine, sane reversion
        target for this trade: either it sits on the WRONG side of entry
        (the band shifted since the trade was taken), or it's closer to
        entry than the stop distance (would guarantee a sub-1:1 reward:risk
        even at a 100% win rate, which is not a bet worth taking regardless
        of how often it wins).
        """
        risk_dist = abs(setup.entry_price - stop_price)
        if setup.direction == "long":
            fallback = setup.entry_price + risk_dist * self.reward_risk
        else:
            fallback = setup.entry_price - risk_dist * self.reward_risk

        bb_mid = window.iloc[-1]["bb_mid"]
        if pd.isna(bb_mid):
            return fallback

        if setup.direction == "long":
            if bb_mid > setup.entry_price and (bb_mid - setup.entry_price) >= risk_dist:
                return float(bb_mid)
            return fallback
        else:
            if bb_mid < setup.entry_price and (setup.entry_price - bb_mid) >= risk_dist:
                return float(bb_mid)
            return fallback

    def position_size(self, risk_amount: float, entry_price: float, stop_price: float) -> float:
        risk_dist = abs(entry_price - stop_price)
        return risk_amount / risk_dist if risk_dist else 0.0

    def check_exit(self, direction: str, entry_price: float, stop_price: float, target_price: float,
                    bar: pd.Series) -> Optional[ExitResult]:
        """
        Unlike the other three strategies, the win case here can NOT
        hardcode self.reward_risk -- compute_take_profit() may have
        targeted bb_mid, which is not guaranteed to sit exactly
        risk_dist * reward_risk away from entry. The actual realized
        R-multiple is computed from entry_price/stop_price/target_price
        directly instead. The loss case is unaffected: stop distance
        defines "1R" risk by construction regardless of what the target
        was, so a stop-out is always exactly -1.0.
        """
        risk_dist = abs(entry_price - stop_price)
        if direction == "long":
            if bar["low"] <= stop_price:
                return ExitResult("loss", stop_price, -1.0)
            if bar["high"] >= target_price:
                r = (target_price - entry_price) / risk_dist if risk_dist else 0.0
                return ExitResult("win", target_price, r)
        else:
            if bar["high"] >= stop_price:
                return ExitResult("loss", stop_price, -1.0)
            if bar["low"] <= target_price:
                r = (entry_price - target_price) / risk_dist if risk_dist else 0.0
                return ExitResult("win", target_price, r)
        return None
