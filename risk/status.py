"""
Risk engine current-state snapshot -- Milestone 6 (second batch).

Distinct from risk/risk_engine.py's evaluate_trade(), which evaluates one
SPECIFIC proposal against the account's state -- this reports where the
account currently stands against every configured limit with NO proposal
in the picture, for the Risk page ("is the guardrail actually working").
Reuses db.repository.build_portfolio_state() directly (the same function
evaluate_trade() itself is fed) so there is one source of truth for
account state, not a second computation of it.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from config.config import RiskConfig
from db.repository import build_portfolio_state


@dataclass
class CorrelatedGroupExposure:
    symbols: List[str]
    notional: float
    exposure_pct: float


@dataclass
class RiskStatus:
    # Configured limits (config/config.py's RiskConfig, read not modified)
    risk_per_trade_pct: float
    max_position_size_pct: float
    max_portfolio_exposure_pct: float
    max_correlated_exposure_pct: float
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    max_drawdown_pct: float
    max_open_positions: int
    max_leverage: float
    correlated_groups: List[List[str]]
    # Current usage against those limits, from real open_positions/pnl state
    account_equity: float
    peak_equity: float
    drawdown_pct: float
    daily_pnl_pct: float
    weekly_pnl_pct: float
    open_positions_count: int
    portfolio_exposure_pct: float
    correlated_exposure: List[CorrelatedGroupExposure]


def get_risk_status(session: Session, risk_config: RiskConfig) -> RiskStatus:
    portfolio = build_portfolio_state(session, account_baseline=risk_config.account_size_ngn)
    equity = portfolio.account_equity

    drawdown_pct = (
        (portfolio.peak_equity - equity) / portfolio.peak_equity * 100 if portfolio.peak_equity else 0.0
    )
    total_notional = sum(p.notional for p in portfolio.open_positions)
    portfolio_exposure_pct = total_notional / equity * 100 if equity else 0.0

    correlated_exposure = []
    for group in risk_config.correlated_groups:
        notional = sum(p.notional for p in portfolio.open_positions if p.symbol in group)
        correlated_exposure.append(CorrelatedGroupExposure(
            symbols=group,
            notional=round(notional, 2),
            exposure_pct=round(notional / equity * 100, 3) if equity else 0.0,
        ))

    return RiskStatus(
        risk_per_trade_pct=risk_config.risk_per_trade_pct,
        max_position_size_pct=risk_config.max_position_size_pct,
        max_portfolio_exposure_pct=risk_config.max_portfolio_exposure_pct,
        max_correlated_exposure_pct=risk_config.max_correlated_exposure_pct,
        max_daily_loss_pct=risk_config.max_daily_loss_pct,
        max_weekly_loss_pct=risk_config.max_weekly_loss_pct,
        max_drawdown_pct=risk_config.max_drawdown_pct,
        max_open_positions=risk_config.max_open_positions,
        max_leverage=risk_config.max_leverage,
        correlated_groups=risk_config.correlated_groups,
        account_equity=round(equity, 2),
        peak_equity=round(portfolio.peak_equity, 2),
        drawdown_pct=round(drawdown_pct, 3),
        daily_pnl_pct=round(portfolio.daily_pnl_pct, 3),
        weekly_pnl_pct=round(portfolio.weekly_pnl_pct, 3),
        open_positions_count=len(portfolio.open_positions),
        portfolio_exposure_pct=round(portfolio_exposure_pct, 3),
        correlated_exposure=correlated_exposure,
    )
