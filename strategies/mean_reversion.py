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
Take-profit: fixed reward:risk multiple beyond the stop (default 2.0R,
same interface-level choice as every other strategy here -- the
Strategy ABC's compute_take_profit(setup, stop_price) only receives the
entry/stop prices, not the live bb_mid value, so a literal "target the
band's midline" exit isn't expressible without a broader interface change;
a fixed R-multiple target is a legitimate, common way to trade
mean-reversion setups too, not a compromise unique to this project).
Position sizing: risk_amount / stop distance (fixed-fractional risk).
Exit: stop or target hit, whichever comes first on a given bar.
Regime requirement: enforced in confirm_entry rather than
market_regime_requirements() for consistency with the other three
strategies -- see their docstrings for why that architectural choice was
made across the board.

VALIDATION STATUS: NOT VALIDATED -- do not treat this as a live/trusted
setup. Run via backtest/validate_milestone7.py (BTCUSDT, 5yr 4H persisted
history, 2026-08-26):

Full period: 132 trades, 29.5% win rate, expectancy -0.114R.
In-sample (everything before the most recent 365 days): 103 trades, 31.1%
win rate, expectancy -0.068R.
Held-out (most recent 365 days, genuine out-of-sample, NOT used to design
this strategy): 29 trades, 24.1% win rate, expectancy -0.276R -- WORSE
than in-sample, same direction as Pullback's failure mode (no edge
anywhere, not an overfit-then-fail-forward pattern like Breakout).

This is the worst full-period expectancy of the three strategies built so
far, and with the healthiest sample size (132 full / 29 held-out, both
comfortably above this file's n>=5 reliability bar) -- meaning this
conclusion can be held with MORE confidence than Pullback's (38 total
trades), not less. The confirm_entry regime gate is doing exactly what it
was built to do (100% of trades land in `sideways`, since every other
regime is hard-rejected), so this isn't a mis-gated strategy firing in
the wrong regime -- the BB-extreme + RSI-extreme entry condition itself,
even restricted to the regime it was designed for, does not show an edge
on BTC 4H.

Candidate revision direction: a fixed 2.0R target may be poorly suited to
mean reversion specifically -- a reversion trade is a bet on a bounce
back toward the band's midline, a smaller expected move than a full 2R
extension, so many winning bounces may be reversing back through
break-even before ever reaching a 2R target that was sized for a
trend-following setup. Testing a tighter reward:risk (e.g. 1.0-1.5R) or a
literal bb_mid target would require extending compute_take_profit's
signature (it currently only receives entry/stop prices, not the live
band values) -- a real interface change, not attempted here.

Kept in the codebase (not deleted), same "pause, don't delete" precedent
as Breakout/Pullback. Not registered in strategies/registry.py or
exposed on the frontend Strategies page while unvalidated.
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
