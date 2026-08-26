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

VALIDATION STATUS: ASSET-SPECIFIC -- NOT VALIDATED on BTCUSDT, VALIDATED
on ETHUSDT. This is the same strategy code and the same fixed parameters
(no per-asset tuning) tested against two different assets' persisted 5yr
4H history via backtest/validate_milestone7.py --symbol=<X>.

--- BTCUSDT (2026-08-26): NOT VALIDATED ---
Full period: 126 trades, 40.5% win rate, expectancy +0.214R.
In-sample (everything before the most recent 365 days): 99 trades, 43.4%
win rate, expectancy +0.303R -- looks like a real edge on its own.
Held-out (most recent 365 days, genuine out-of-sample, NOT used to design
this strategy): 27 trades, win rate drops to 29.6%, expectancy flips to
-0.111R. This is not "the edge weakened" -- it's a full sign flip, meaning
the full-period/in-sample positive number was substantially an artifact
of the specific years backtested, not a property of the entry logic that
generalizes forward. Regime breakdown shows the strategy's trades landing
mostly in the `sideways` classification (62/126) at entry time, which
tracks mechanically -- a fresh range breakout is often still classified
`sideways` by the 20-bar-EMA-slope regime classifier at the moment it
fires, since the slope hasn't caught up yet.

--- ETHUSDT (2026-08-26): VALIDATED ---
Full period: 126 trades, 39.7% win rate, expectancy +0.19R.
In-sample: 104 trades, 40.4% win rate, expectancy +0.212R.
Held-out (most recent 365 days, genuine out-of-sample): 22 trades, win
rate 36.4%, expectancy +0.091R. The sign HELD (positive in-sample AND
held-out) -- a real weakening from in-sample to held-out (not "held
steady"), but the same directional pattern as TrendContinuationBOS's own
original EMA21 filter validation, and with a LARGER held-out sample
(22 trades here vs. 10-14 there). This clears this project's own
established bar: positive held-out expectancy, n>=5, same sign as
in-sample. Regime breakdown on ETH: `sideways` (51 trades, +0.412R) is
this strategy's BEST regime here -- notably the OPPOSITE of
TrendContinuationBOS's own ETH result, where `sideways` is one of its
worst regimes (-0.385R, see trend_continuation_bos.py) -- confirming this
is a genuinely different edge, not a re-discovery of BOS's ETH behavior
under a different name. `weak_bull_trend` (53 trades, +0.189R) is also
positive; `strong_bull_trend` (-0.250R) and `strong_bear_trend` (-0.400R)
are negative, both modest-sized buckets (12 and 10 trades).

Held-out sample sizes are modest on both assets (27 BTC, 22 ETH) --
normal caveat that exact magnitudes aren't precise, direction is what's
trustworthy. Kept in the codebase as NOT VALIDATED for BTC (candidate
revision directions unchanged: requiring TrendState.RANGE specifically,
or gating out `strong_bear_trend`) and VALIDATED for ETH specifically --
this validation is NOT yet wired into strategies/registry.py, MARKET.pairs,
or paper_trading/engine.py. Doing so requires a real architecture change
(today's code hardcodes ONE strategy applied uniformly across every
symbol in MARKET.pairs -- there is no per-symbol strategy concept yet)
AND a mandatory re-derivation of max_portfolio_exposure_pct/
max_correlated_exposure_pct in config.py, which are currently 85% only
because exactly one position is ever open at a time (see config.py's own
comments) -- a second concurrent BTC+ETH position becomes real the
moment this is wired in. See docs/ARCHITECTURE.md's Milestone 10 section
for the full scoping; nothing has been wired in as of this writing.
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
