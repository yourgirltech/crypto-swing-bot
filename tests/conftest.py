"""
Shared fixtures. Tests use their OWN explicit RiskConfig values rather than
config.config.RISK, so a deliberate recalibration of a live limit (e.g.
max_portfolio_exposure_pct 85% -> 90%) never breaks a test that is only
checking the rule's logic -- and a test never silently depends on a
number that is supposed to be re-derived from data.
"""

import pytest

from config.config import RiskConfig
from proposals.trade_proposal import TradeProposal
from risk.position_sizing import PortfolioState


@pytest.fixture
def risk():
    return RiskConfig(
        account_size_ngn=1_000_000.0,
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        max_weekly_loss_pct=6.0,
        max_open_positions=2,
        max_leverage=1.0,
        max_position_size_pct=85.0,
        max_portfolio_exposure_pct=90.0,
        max_drawdown_pct=15.0,
        max_correlated_exposure_pct=90.0,
        correlated_groups=[["BTCUSDT", "ETHUSDT"]],
    )


@pytest.fixture
def flat_portfolio():
    """At-rest account: no drawdown, no PnL today/this week, nothing open."""
    return PortfolioState(account_equity=1_000_000.0, peak_equity=1_000_000.0)


def make_proposal(**overrides) -> TradeProposal:
    """
    A proposal that passes every risk check against `risk` + `flat_portfolio`:
    entry 100, stop 98 (2 pts), 5,000 units -> 10,000 at risk (1.0%),
    500,000 notional (50% of equity, 0.5x leverage).
    """
    fields = dict(
        symbol="BTCUSDT", setup_type="trend_continuation_bos", direction="long",
        entry_price=100.0, stop_price=98.0, target_price=104.0,
        risk_amount=10_000.0, position_size=5_000.0, reward_risk_ratio=2.0,
        trend="uptrend", regime="strong_bull_trend", rsi=55.0,
        backtested_win_rate_pct=None, backtested_sample_size=None, backtested_expectancy_r=None,
        notes="",
    )
    fields.update(overrides)
    return TradeProposal(**fields)
