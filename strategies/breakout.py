"""
Breakout strategy -- Milestone 7's first new Strategy alongside
TrendContinuationBOS.

Entry: a Donchian-channel break -- the current bar closes beyond the
highest high (long) or lowest low (short) of the `channel_lookback` bars
BEFORE it (the current bar is excluded from the channel itself, so this
is a genuine no-lookahead break of the prior range, not a break of a
range that already includes today's extreme). Confirmed by an ATR
expansion filter: current ATR must sit at least `min_atr_expansion`x
above its own trailing average, so a break on a dead/contracting range
(low conviction, likely to fail) is skipped.

This is deliberately a DIFFERENT structural idea from TrendContinuationBOS,
not a re-skin of it:
- TrendContinuationBOS only fires once a trend is ALREADY established
  (classify_trend says UPTREND/DOWNTREND) and a fresh BOS confirms it.
- Breakout fires on the range -> trend TRANSITION itself -- it does not
  require trend_state to be anything in particular, and does not use the
  swing/BOS machinery to define its entry at all (it ignores the `swings`/
  `trend_state`/`signal` arguments other than what confirm_entry does with
  regime). A consolidation breaking out of its own range, before the
  swing engine has enough new HH/HL evidence to call it an uptrend, is
  exactly the case this strategy exists to catch.

Confirmation: rejects entries where RSI is already beyond the extreme
band (default 20/80) in the breakout's own direction -- avoids chasing a
breakout that's already a blow-off move on the print itself.

Invalidation: none defined, same as TrendContinuationBOS -- entries
trigger immediately on the breaking bar, there is no pending multi-bar
setup window to invalidate before a fill.

Stop-loss: ATR-multiple beyond entry (default 2.0x ATR14 -- wider than
TrendContinuationBOS's 1.5x, since a fresh breakout has no established
trend structure yet to anchor a tighter stop against).
Take-profit: fixed reward:risk multiple beyond the stop (default 2.0R).
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: none hard-excluded at market_regime_requirements()
level -- confirm_entry only screens on RSI extremity, not regime, since
breakouts are exactly the mechanism by which a regime like `sideways`
transitions into a trending one; excluding sideways-regime entries here
would exclude the strategy's own reason for existing.

VALIDATION STATUS: NOT VALIDATED -- do not treat this as a live/trusted
setup. Run via backtest/validate_milestone7.py (BTCUSDT, 5yr 4H persisted
history, 2026-08-26):

Full period: 126 trades, 40.5% win rate, expectancy +0.214R.
In-sample (everything before the most recent 365 days): 99 trades, 43.4%
win rate, expectancy +0.303R -- looks like a real edge on its own.

Held-out (most recent 365 days, genuine out-of-sample, NOT used to design
this strategy): 27 trades, win rate drops to 29.6%, expectancy flips to
-0.111R. This is not "the edge weakened" (like weak_bull_trend's filter,
which stayed negative in the SAME direction both in-sample and held-out)
-- it's a full sign flip, meaning the full-period/in-sample positive
number was substantially an artifact of the specific years backtested,
not a property of the entry logic that generalizes forward. Regime
breakdown shows the strategy's trades landing mostly in the `sideways`
classification (62/126) at entry time, which tracks mechanically -- a
fresh range breakout is often still classified `sideways` by the
20-bar-EMA-slope regime classifier at the moment it fires, since the
slope hasn't caught up yet.

Held-out sample is small (27 trades) -- normal caveat that magnitude
isn't precise -- but the sign flip itself, on a channel/ATR-expansion
rule with no parameters chosen by looking at this data, is a real signal
that this specific entry definition doesn't have a robust edge as-is, not
noise. Kept in the codebase (not deleted) as a base to iterate on --
candidate directions for a future revision: requiring TrendState.RANGE
specifically (rather than allowing entries during an already-trending
market, which may be catching momentum exhaustion instead of a genuine
consolidation break), or gating out the `strong_bear_trend` regime
(5 trades, -0.400R, the worst full-period bucket).
"""

from typing import Optional, Set

import pandas as pd

from strategies.base import EntrySetup, ExitResult, Strategy
from structure.market_structure import TrendState


class Breakout(Strategy):
    name = "breakout"

    def __init__(self, channel_lookback: int = 20, atr_stop_mult: float = 2.0,
                 reward_risk: float = 2.0, min_atr_expansion: float = 1.1,
                 rsi_extreme: tuple = (20, 80)):
        self.channel_lookback = channel_lookback
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.min_atr_expansion = min_atr_expansion
        self.rsi_extreme = rsi_extreme
        # Only used by run_backtest()'s SwingTracker construction (every
        # Strategy is expected to expose this -- see backtest_engine.py);
        # this strategy doesn't use swings itself, so the exact value
        # barely matters, but it must exist and be reasonable.
        self.swing_lookback = 5

    def market_regime_requirements(self) -> Optional[Set[str]]:
        return None  # see module docstring -- deliberately not regime-gated at this level

    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        min_bars = self.channel_lookback + 15  # + ATR trailing-average warmup
        if len(window) < min_bars:
            return None

        bar = window.iloc[-1]
        atr_val = bar["atr"]
        if pd.isna(atr_val):
            return None

        # Channel over the N bars BEFORE the current one -- current bar's
        # own high/low is excluded, so a break is judged against the PRIOR
        # range, not a range that already includes today's extreme.
        prior = window.iloc[-(self.channel_lookback + 1):-1]
        channel_high = prior["high"].max()
        channel_low = prior["low"].min()

        atr_avg = window["atr"].tail(self.channel_lookback * 3).mean()
        if pd.isna(atr_avg) or atr_avg == 0:
            return None
        atr_ratio = atr_val / atr_avg
        if atr_ratio < self.min_atr_expansion:
            return None  # break without volatility expansion -- low conviction, skip

        close = float(bar["close"])
        if close > channel_high:
            direction = "long"
            breakout_level = channel_high
        elif close < channel_low:
            direction = "short"
            breakout_level = channel_low
        else:
            return None

        breakout_margin_pct = (
            (close - breakout_level) / breakout_level * 100 if direction == "long"
            else (breakout_level - close) / breakout_level * 100
        )

        diagnostics = {
            "rsi_at_entry": float(bar["rsi"]),
            "atr_pct_at_entry": float(atr_val / close * 100),
            "dist_from_ema_fast_pct": float((close - bar["ema_21"]) / bar["ema_21"] * 100),
            "dist_from_ema_slow_pct": float((close - bar["ema_50"]) / bar["ema_50"] * 100),
            "breakout_margin_pct": float(breakout_margin_pct),
            "bars_since_swing": None,  # not a swing-based setup -- see module docstring
        }
        return EntrySetup(direction=direction, entry_price=close, diagnostics=diagnostics)

    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        rsi_val = diagnostics["rsi_at_entry"]
        return self.rsi_extreme[0] < rsi_val < self.rsi_extreme[1]

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
