"""
Strategy interface -- Milestone 3.

Every trading idea (current and future -- see MASTER_PLAN.md Milestone 7)
implements this ABC so backtest_engine.run_backtest() and
proposals.trade_proposal.build_proposal() can both run ANY strategy
without either one knowing that strategy's specifics.

This is not abstraction for its own sake: before this module existed, the
trend-continuation BOS entry/stop/target/confirmation logic was written
twice -- once inside run_backtest(), once (kept manually in sync via a
comment) inside build_proposal() -- with a real risk of the two drifting
apart. Both call sites now go through one Strategy instance instead.

Each abstract method below maps to one decision a discretionary trader
would name out loud when describing a setup: entry, confirmation,
invalidation, stop-loss, take-profit, position sizing, exit, and which
market regime(s) it's meant for.

A Strategy instance is stateless -- every method takes whatever data it
needs as arguments rather than holding open-position state itself, so one
instance can be reused freely across symbols, backtests, and the live
proposal path.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Set

import pandas as pd

from structure.market_structure import TrendState


@dataclass
class EntrySetup:
    """A structurally valid entry candidate, before confirmation is applied."""
    direction: str          # "long" | "short"
    entry_price: float
    diagnostics: dict       # rsi_at_entry, atr_pct_at_entry, dist_from_ema_fast_pct,
                             # dist_from_ema_slow_pct, breakout_margin_pct, bars_since_swing


@dataclass
class ExitResult:
    outcome: str            # "win" | "loss"
    exit_price: float
    r_multiple: float


class Strategy(ABC):
    name: str

    @abstractmethod
    def market_regime_requirements(self) -> Optional[Set[str]]:
        """
        Which regime(s) (regime.regime_classifier.classify_regime's labels)
        this strategy requires. None means "not hard-gated by regime at
        this level" -- a strategy can still react differently per-regime
        inside confirm_entry (e.g. a regime-specific confirmation filter)
        without excluding any regime outright here.
        """

    @abstractmethod
    def check_entry(self, window: pd.DataFrame, swings: list, trend_state: TrendState,
                     signal: Optional[str]) -> Optional[EntrySetup]:
        """
        Structural entry condition, evaluated on a no-lookahead window (all
        bars up to and including the current one). Returns an EntrySetup if
        met, else None. Does NOT apply confirmation -- kept separate so a
        strategy's core structural idea and its regime-specific filters can
        be reasoned about and iterated on independently.
        """

    @abstractmethod
    def confirm_entry(self, regime: str, diagnostics: dict) -> bool:
        """
        Additional confirmation gating a structurally-valid EntrySetup.
        Return False to skip this entry. Regime-specific confirmation
        rules live here, as part of the strategy itself.
        """

    @abstractmethod
    def check_invalidation(self, setup: EntrySetup, window: pd.DataFrame) -> bool:
        """
        Whether a structurally-valid, confirmed setup should be abandoned
        before it's actually taken. Return True to invalidate.
        """

    @abstractmethod
    def compute_stop_loss(self, setup: EntrySetup, window: pd.DataFrame) -> float:
        """Stop-loss price for a confirmed, non-invalidated setup."""

    @abstractmethod
    def compute_take_profit(self, setup: EntrySetup, stop_price: float, window: pd.DataFrame) -> float:
        """
        Take-profit price for a confirmed, non-invalidated setup. `window`
        is the same no-lookahead window check_entry/compute_stop_loss see
        -- added so a strategy CAN target something other than a fixed
        reward:risk multiple (e.g. a Bollinger Band midline for a
        mean-reversion setup) when its own trade shape calls for it. A
        strategy that just wants a fixed R-multiple is free to ignore this
        argument entirely -- see TrendContinuationBOS/Breakout/Pullback/
        RangeTrading, none of which use it.
        """

    @abstractmethod
    def position_size(self, risk_amount: float, entry_price: float, stop_price: float) -> float:
        """Units to buy/sell so risk_amount is what's actually at risk to the stop."""

    @abstractmethod
    def check_exit(self, direction: str, entry_price: float, stop_price: float, target_price: float,
                    bar: pd.Series) -> Optional[ExitResult]:
        """
        Checks ONE bar of an already-open position against this strategy's
        exit rule. Returns an ExitResult if the position closes on this
        bar, else None (still open).

        `entry_price` was added alongside compute_take_profit()'s `window`
        param (see there) for the same reason: once a strategy's target
        isn't guaranteed to be exactly stop_dist * some fixed
        reward:risk away (e.g. MeanReversion's bb_mid target), the actual
        realized R-multiple on a win depends on entry_price too, not just
        stop/target. A strategy whose target IS always a fixed multiple of
        the stop distance can keep returning that constant on a win and
        ignore this argument -- see TrendContinuationBOS/Breakout/
        Pullback/RangeTrading. The loss case is unaffected either way:
        stop distance defines "1R" risk by construction, so a stop-out is
        always exactly -1.0 regardless of what the target was.
        """
