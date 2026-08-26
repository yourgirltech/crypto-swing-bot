"""
Risk Management Engine — Milestone 2.

An ACTIVE GATE with veto authority, not just config values sitting unused.
`evaluate_trade()` takes a TradeProposal plus a PortfolioState snapshot and
returns a RiskVerdict: APPROVE, or REJECT with a specific human-readable
reason. `build_proposal()` (proposals/trade_proposal.py) decides IF a setup
exists; this module decides whether it's safe to take GIVEN CURRENT
PORTFOLIO RISK. Neither module knows about the other's job.

Rule order is deliberate:
1. Circuit breakers (max drawdown, daily loss, weekly loss) are account-wide
   kill switches, independent of the specific proposal. If one has already
   tripped, no proposal should pass — checked first, full stop.
2. Mandatory stop-loss — a structural sanity check on the proposal itself.
3. Per-trade sizing checks (leverage, risk-per-trade, position size).
4. Portfolio-wide checks (open positions count, total exposure, correlated
   exposure) — these need to know what's already open.

Correlated exposure: RiskConfig.correlated_groups groups symbols that move
together (BTC+ETH is the one group defined for now, confirmed with user
2026-08-25). ETH is paused (config.MarketConfig), so today this group only
ever contains BTC and the check has nothing to bite on — it's written
generically so it's already correct once ETH trading resumes, not because
it does anything interesting right now.

RESOLVED as of Milestone 4: `main.py`'s demo path used to call
`evaluate_trade()` with an empty/at-rest `PortfolioState` because there
was no real fills history to build one from (see
`db.repository.build_portfolio_state()`, now backed by real
`paper_trades` rows). That query still returns an empty/at-rest state
before any paper trade has ever closed — which is correct (there IS no
history yet), not a stub standing in for missing data.

`RiskVerdict.metrics` carries every numeric quantity computed along the
way (not just pass/fail), specifically so `reporting/plain_language_
summary.py`'s full trade review doesn't have to re-derive the same
percentages from scratch — one source of truth for "how much of each
budget this trade would use."

RECALIBRATED as of Milestone 4's position-sizing fix (2026-08-25): the
max_position_size / max_portfolio_exposure / max_correlated_exposure
checks below are now genuine BACKSTOPS, expected to rarely fire, not the
everyday deciding factor. `risk/position_sizing.py`'s `size_position()`
already sizes a proposal DOWN to satisfy all three before it ever reaches
`evaluate_trade()` — these checks stay here as defense-in-depth (in case
a proposal is ever built via a different path that skips sizing), not as
the primary enforcement mechanism anymore. See risk/position_sizing.py's
module docstring for the full story (a live run first surfaced this as a
20% max_position_size_pct rejecting 96% of real trades; fixed by sizing
down instead of rejecting, then the identical issue was found in
max_portfolio_exposure_pct/max_correlated_exposure_pct and fixed the same way).
"""

from dataclasses import dataclass, field
from typing import Optional

from config.config import RiskConfig
from proposals.trade_proposal import TradeProposal
# OpenPosition/PortfolioState live in risk/position_sizing.py (not here) to
# avoid a circular import -- trade_proposal.py needs them too, and this
# module already imports TradeProposal from trade_proposal.py. Re-exported
# here for backward compatibility with existing `from risk.risk_engine
# import OpenPosition, PortfolioState` call sites (e.g. db/repository.py).
from risk.position_sizing import OpenPosition, PortfolioState, correlated_group as _correlated_group

__all__ = ["OpenPosition", "PortfolioState", "RiskVerdict", "evaluate_trade"]


@dataclass
class RiskVerdict:
    approved: bool
    reason: Optional[str] = None   # None iff approved
    checks: dict = field(default_factory=dict)   # every rule's pass/fail, for audit
    metrics: dict = field(default_factory=dict)  # the numbers behind those checks, for reporting


def evaluate_trade(proposal: TradeProposal, portfolio: PortfolioState, risk: RiskConfig) -> RiskVerdict:
    checks = {}
    metrics = {}
    equity = portfolio.account_equity
    notional = proposal.position_size * proposal.entry_price

    # 1. Circuit breakers / kill switches — account-wide, checked first,
    # independent of this specific proposal.
    drawdown_pct = (
        (portfolio.peak_equity - portfolio.account_equity) / portfolio.peak_equity * 100
        if portfolio.peak_equity else 0.0
    )
    metrics["drawdown_pct"] = drawdown_pct
    checks["max_drawdown"] = drawdown_pct <= risk.max_drawdown_pct
    if not checks["max_drawdown"]:
        return RiskVerdict(False, (
            f"Max drawdown breached: {drawdown_pct:.2f}% >= {risk.max_drawdown_pct:.2f}% limit. "
            "All new trades halted until reviewed."
        ), checks, metrics)

    metrics["daily_pnl_pct"] = portfolio.daily_pnl_pct
    checks["max_daily_loss"] = portfolio.daily_pnl_pct > -risk.max_daily_loss_pct
    if not checks["max_daily_loss"]:
        return RiskVerdict(False, (
            f"Daily loss circuit breaker tripped: {portfolio.daily_pnl_pct:.2f}% <= "
            f"-{risk.max_daily_loss_pct:.2f}% limit. No new trades today."
        ), checks, metrics)

    metrics["weekly_pnl_pct"] = portfolio.weekly_pnl_pct
    checks["max_weekly_loss"] = portfolio.weekly_pnl_pct > -risk.max_weekly_loss_pct
    if not checks["max_weekly_loss"]:
        return RiskVerdict(False, (
            f"Weekly loss circuit breaker tripped: {portfolio.weekly_pnl_pct:.2f}% <= "
            f"-{risk.max_weekly_loss_pct:.2f}% limit. No new trades this week."
        ), checks, metrics)

    # 2. Mandatory stop-loss.
    stop_dist = abs(proposal.entry_price - proposal.stop_price)
    checks["mandatory_stop_loss"] = stop_dist > 0
    if not checks["mandatory_stop_loss"]:
        return RiskVerdict(False, "Proposal has no valid stop-loss - every trade must have one.", checks, metrics)

    # 3. Max leverage (notional vs equity; max_leverage=1.0 means notional can't exceed equity).
    implied_leverage = notional / equity if equity else float("inf")
    metrics["implied_leverage"] = implied_leverage
    checks["max_leverage"] = implied_leverage <= risk.max_leverage
    if not checks["max_leverage"]:
        return RiskVerdict(False, (
            f"Implied leverage {implied_leverage:.2f}x exceeds max {risk.max_leverage:.2f}x."
        ), checks, metrics)

    # 4. Max risk per trade.
    risk_pct = proposal.risk_amount / equity * 100 if equity else float("inf")
    metrics["risk_pct"] = risk_pct
    checks["max_risk_per_trade"] = risk_pct <= risk.risk_per_trade_pct
    if not checks["max_risk_per_trade"]:
        return RiskVerdict(False, (
            f"Risk on this trade ({risk_pct:.2f}% of equity) exceeds {risk.risk_per_trade_pct:.2f}% limit."
        ), checks, metrics)

    # 5. Max position size.
    position_size_pct = notional / equity * 100 if equity else float("inf")
    metrics["position_size_pct"] = position_size_pct
    checks["max_position_size"] = position_size_pct <= risk.max_position_size_pct
    if not checks["max_position_size"]:
        return RiskVerdict(False, (
            f"Position size ({position_size_pct:.2f}% of equity) exceeds "
            f"{risk.max_position_size_pct:.2f}% limit."
        ), checks, metrics)

    # 6. Max open positions.
    metrics["open_positions_count"] = len(portfolio.open_positions)
    checks["max_open_positions"] = len(portfolio.open_positions) < risk.max_open_positions
    if not checks["max_open_positions"]:
        return RiskVerdict(False, f"Already at max open positions ({risk.max_open_positions}).", checks, metrics)

    # 7. Max portfolio exposure.
    existing_notional = sum(p.notional for p in portfolio.open_positions)
    portfolio_exposure_pct = (existing_notional + notional) / equity * 100 if equity else float("inf")
    metrics["portfolio_exposure_pct"] = portfolio_exposure_pct
    checks["max_portfolio_exposure"] = portfolio_exposure_pct <= risk.max_portfolio_exposure_pct
    if not checks["max_portfolio_exposure"]:
        return RiskVerdict(False, (
            f"Total portfolio exposure would be {portfolio_exposure_pct:.2f}% of equity, "
            f"exceeds {risk.max_portfolio_exposure_pct:.2f}% limit."
        ), checks, metrics)

    # 8. Max correlated exposure (e.g. BTC+ETH counted together).
    group = _correlated_group(proposal.symbol, risk.correlated_groups)
    correlated_notional = sum(p.notional for p in portfolio.open_positions if p.symbol in group)
    correlated_exposure_pct = (correlated_notional + notional) / equity * 100 if equity else float("inf")
    metrics["correlated_exposure_pct"] = correlated_exposure_pct
    metrics["correlated_group"] = group
    checks["max_correlated_exposure"] = correlated_exposure_pct <= risk.max_correlated_exposure_pct
    if not checks["max_correlated_exposure"]:
        return RiskVerdict(False, (
            f"Correlated exposure ({'+'.join(group)}) would be {correlated_exposure_pct:.2f}% of "
            f"equity, exceeds {risk.max_correlated_exposure_pct:.2f}% limit."
        ), checks, metrics)

    return RiskVerdict(True, None, checks, metrics)
