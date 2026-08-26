"""
Range trading strategy -- Milestone 7's fourth and final new Strategy.

Entry: a structural bounce off a support/resistance zone (from
structure/market_structure.py's build_sr_zones, built from swing
highs/lows the same swing engine every other strategy shares), gated
hard on TrendState.RANGE. This is the structural counterpart to
MeanReversion's statistical one (Bollinger Band + RSI extremes): both
express "expect a bounce, not a breakout" but from different evidence --
MeanReversion from price/momentum statistics, RangeTrading from the
swing-derived support/resistance structure itself.

Long: the current bar's low touches or pierces the nearest support zone
BELOW price, and the bar's close reclaims back above that zone's lower
edge (a bounce confirmation on this exact bar, not a stale touch from
several bars ago). Short: symmetric off the nearest resistance zone
above price. Requires TrendState.RANGE specifically (the swing HH/HL/
LH/LL sequence itself reads as non-trending) -- a stricter, different
gate than MeanReversion's `sideways` REGIME requirement (EMA-slope/ATR
derived). The two can and will disagree on some bars; that's expected,
since they're independently-derived signals of the same underlying idea.

Confirmation: none beyond the structural touch-and-reclaim itself --
unlike the other three strategies, there is no RSI/regime screen here,
since TrendState.RANGE (from check_entry) and the existence of a
touched-and-reclaimed zone already encode this setup's core thesis.

Invalidation: none defined, same as the other three strategies -- the
entry triggers immediately on the bounce-confirmation bar itself.

Stop-loss: ATR-multiple beyond entry (default 1.5x ATR14, consistent
with TrendContinuationBOS/Pullback/MeanReversion).
Take-profit: fixed reward:risk multiple beyond the stop (default 2.0R --
see docs/ARCHITECTURE.md's Milestone 7 cross-cutting note on why this
shared target, inherited from TrendContinuationBOS, may not suit a
range-bounce trade shape any better than it suited MeanReversion's).
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: gated via TrendState in check_entry itself (not
confirm_entry) since the range condition IS this strategy's core
structural thesis, not an additional filter layered on top of a
separately-defined entry -- a deliberate difference from the other three
strategies' architecture, where the core entry condition and the regime/
trend gate are two separate concerns.

VALIDATION STATUS: NOT VALIDATED -- do not treat this as a live/trusted
setup, though this is the closest of the four Milestone 7 strategies to
passing. Run via backtest/validate_milestone7.py (BTCUSDT, 5yr 4H
persisted history, 2026-08-26):

Full period: 627 trades (by far the largest sample of any strategy here
-- TrendState.RANGE fires often, since it only needs a mixed recent
HH/HL/LH/LL sequence), 37.2% win rate, expectancy +0.115R.
In-sample (everything before the most recent 365 days): 489 trades, 38.4%
win rate, expectancy +0.153R.
Held-out (most recent 365 days, genuine out-of-sample, NOT used to design
this strategy): 138 trades, 32.6% win rate, expectancy -0.022R.

The held-out result is technically negative, so this fails the file's own
validation bar (expectancy_r > 0) -- but -0.022R is close to break-even,
not a clear negative signal like Pullback (-0.143R) or Mean-reversion
(-0.276R). This is directionally the same shape as Breakout's failure
(positive in-sample, negative held-out), but far milder in magnitude --
"the edge didn't survive out-of-sample" is a fair description, "the edge
inverted" is not, for this one specifically. Held-out max drawdown is a
real concern regardless of the expectancy discussion: -40.86%, the
largest of any strategy/slice built so far -- meaningful risk exposure
even at a near-flat expectancy.

Notable and worth taking at face value rather than glossing over: the
regime breakdown shows this strategy's actual positive expectancy
concentrated in `weak_bull_trend` (+0.200R, 275 trades) and
`strong_bull_trend` (+0.500R, 16 trades) bars -- NOT in `sideways`
(+0.034R, barely positive, 322 trades, its largest bucket), which is
where a "range trading" strategy would be expected to perform best if its
thesis were clean. This is exactly the TrendState-vs-Regime disagreement
described above in practice: many TrendState.RANGE bars occur DURING
periods the separate EMA-slope-based regime classifier still calls a bull
trend (a consolidation/whipsaw within an uptrend, not genuine
range-bound sideways action) -- meaning whatever edge exists here may not
actually be "range trading" in the sense the regime label implies.
`strong_bear_trend` is negative (-0.077R, 13 trades, too few to weigh
heavily).

Same cross-cutting caveat as Breakout/Pullback/Mean-reversion applies:
this was tested against the shared fixed 2.0R target inherited from
TrendContinuationBOS, not a target chosen for a bounce-off-a-zone trade
shape -- see docs/ARCHITECTURE.md's Milestone 7 note.

Kept in the codebase (not deleted), not registered in
strategies/registry.py or exposed on the frontend Strategies page while
unvalidated.
"""

from typing import Optional, Set

import pandas as pd

from strategies.base import EntrySetup, ExitResult, Strategy
from structure.market_structure import TrendState, build_sr_zones


class RangeTrading(Strategy):
    name = "range_trading"

    def __init__(self, atr_stop_mult: float = 1.5, reward_risk: float = 2.0):
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.swing_lookback = 5  # also feeds build_sr_zones' input swings via run_backtest's SwingTracker

    def market_regime_requirements(self) -> Optional[Set[str]]:
        return None  # gated via TrendState in check_entry itself -- see module docstring

    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        if trend_state != TrendState.RANGE:
            return None

        bar = window.iloc[-1]
        atr_val = bar["atr"]
        if pd.isna(atr_val):
            return None

        zones = build_sr_zones(swings)
        if not zones:
            return None

        close = float(bar["close"])
        supports = [z for z in zones if z.kind == "support" and z.price_high <= close]
        resistances = [z for z in zones if z.kind == "resistance" and z.price_low >= close]

        direction = None
        triggering_zone = None
        if supports:
            nearest_support = max(supports, key=lambda z: z.price_high)
            if bar["low"] <= nearest_support.price_high and close > nearest_support.price_low:
                direction = "long"
                triggering_zone = nearest_support
        if direction is None and resistances:
            nearest_resistance = min(resistances, key=lambda z: z.price_low)
            if bar["high"] >= nearest_resistance.price_low and close < nearest_resistance.price_high:
                direction = "short"
                triggering_zone = nearest_resistance

        if direction is None:
            return None

        zone_ref_price = (triggering_zone.price_low + triggering_zone.price_high) / 2
        bounce_margin_pct = (
            (close - zone_ref_price) / zone_ref_price * 100 if direction == "long"
            else (zone_ref_price - close) / zone_ref_price * 100
        )
        bars_since_zone = (len(window) - 1) - triggering_zone.origin_index

        diagnostics = {
            "rsi_at_entry": float(bar["rsi"]),
            "atr_pct_at_entry": float(atr_val / close * 100),
            "dist_from_ema_fast_pct": float((close - bar["ema_21"]) / bar["ema_21"] * 100),
            "dist_from_ema_slow_pct": float((close - bar["ema_50"]) / bar["ema_50"] * 100),
            "breakout_margin_pct": float(bounce_margin_pct),  # reused field: distance from the triggering zone, not a breakout
            "bars_since_swing": int(bars_since_zone),
        }
        return EntrySetup(direction=direction, entry_price=close, diagnostics=diagnostics)

    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        return True  # see module docstring -- TrendState.RANGE in check_entry already IS this strategy's gate

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
