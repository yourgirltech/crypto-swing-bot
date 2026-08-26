"""
Shared position sizing -- used by both backtest_engine.run_backtest() and
proposals.trade_proposal.build_proposal() so backtested expectancy and live
position sizing are computed by the exact same rule (the same "don't
duplicate the same logic in two places" principle Milestone 3 applied to
entry/stop/target logic, now applied to sizing).

Confirmed with the user 2026-08-25, in two stages:

1. Rather than loosening max_position_size_pct to accommodate every trade
   at full risk_per_trade_pct (which was the original, rejected proposal),
   position sizing itself takes the size that satisfies risk_per_trade_pct
   UNLESS a notional cap is tighter, in which case it sizes DOWN and risks
   LESS than risk_per_trade_pct on that one trade -- never rejected
   outright, never sized UP past the risk-based target.

2. That same day, a live run showed the identical miscalibration also
   affects max_portfolio_exposure_pct and max_correlated_exposure_pct (with
   ETH paused, a single open BTC position's own notional IS the portfolio
   exposure AND the correlated exposure -- nothing else to sum against).
   size_position() now sizes down for ALL THREE constraints together,
   taking whichever leaves the least room, not just the single-trade cap.

Kept in its own module (not risk/risk_engine.py) to avoid a circular
import: risk_engine.py imports TradeProposal from proposals/trade_proposal.py,
and trade_proposal.py needs this module's types/function -- putting this
here (not risk_engine.py) means neither trade_proposal.py nor risk_engine.py
has to import the other. risk_engine.py re-exports OpenPosition/
PortfolioState from here for backward compatibility with existing imports
(e.g. db/repository.py's `from risk.risk_engine import OpenPosition, ...`).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class OpenPosition:
    """One currently-open position, as far as sizing/risk checks need to know."""
    symbol: str
    direction: str      # "long" | "short"
    notional: float      # position_size * entry_price


@dataclass
class PortfolioState:
    """Snapshot of account state at evaluation/sizing time. See db.repository.build_portfolio_state()."""
    account_equity: float
    peak_equity: float
    open_positions: List[OpenPosition] = field(default_factory=list)
    daily_pnl_pct: float = 0.0     # e.g. -2.5 = down 2.5% today
    weekly_pnl_pct: float = 0.0


@dataclass
class SizingResult:
    position_size: float
    risk_amount: float        # ACTUAL $ at risk to the stop -- may be less than the risk-based target
    was_capped: bool           # True if some cap bound tighter than the risk-based size
    binding_constraint: str    # "risk_based" | "position_cap" | "portfolio_cap" | "correlated_cap"


def correlated_group(symbol: str, groups: List[List[str]]) -> List[str]:
    for group in groups:
        if symbol in group:
            return group
    return [symbol]


def size_position(risk_based_size: float, entry_price: float, stop_price: float, symbol: str,
                   portfolio: PortfolioState, max_position_size_pct: float,
                   max_portfolio_exposure_pct: float, max_correlated_exposure_pct: float,
                   correlated_groups: List[List[str]]) -> SizingResult:
    """
    risk_based_size: what Strategy.position_size() computed, targeting
    risk_per_trade_pct exactly. Never sized UP past that -- only down, to
    whichever of the three caps below leaves the least room:

    - position_cap: this trade's own notional vs. max_position_size_pct of equity.
    - portfolio_cap: this trade's notional PLUS all other open positions'
      notional vs. max_portfolio_exposure_pct of equity.
    - correlated_cap: this trade's notional PLUS open positions in the same
      correlated_groups entry vs. max_correlated_exposure_pct of equity.

    With no other positions open (the common case today, BTC-only), the
    portfolio/correlated caps reduce to their full percentage of equity --
    this trade is the only thing being measured against them.
    """
    equity = portfolio.account_equity
    group = correlated_group(symbol, correlated_groups)
    existing_portfolio_notional = sum(p.notional for p in portfolio.open_positions)
    existing_correlated_notional = sum(p.notional for p in portfolio.open_positions if p.symbol in group)

    caps_notional = {
        "position_cap": equity * max_position_size_pct / 100,
        "portfolio_cap": max(0.0, equity * max_portfolio_exposure_pct / 100 - existing_portfolio_notional),
        "correlated_cap": max(0.0, equity * max_correlated_exposure_pct / 100 - existing_correlated_notional),
    }
    binding_constraint, tightest_notional = min(caps_notional.items(), key=lambda kv: kv[1])
    cap_size = tightest_notional / entry_price if entry_price else 0.0

    if risk_based_size <= cap_size:
        position_size = risk_based_size
        binding_constraint = "risk_based"
        was_capped = False
    else:
        position_size = cap_size
        was_capped = True

    stop_dist = abs(entry_price - stop_price)
    risk_amount = position_size * stop_dist
    return SizingResult(position_size=position_size, risk_amount=risk_amount,
                         was_capped=was_capped, binding_constraint=binding_constraint)
