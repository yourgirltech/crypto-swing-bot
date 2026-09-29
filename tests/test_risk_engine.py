"""
risk/risk_engine.py's evaluate_trade() -- the veto gate. Each test isolates
one rule by starting from a proposal that passes everything (conftest's
make_proposal) and breaking exactly one thing.
"""

import pytest

from risk.position_sizing import OpenPosition, PortfolioState
from risk.risk_engine import evaluate_trade
from tests.conftest import make_proposal


def test_clean_proposal_is_approved(risk, flat_portfolio):
    verdict = evaluate_trade(make_proposal(), flat_portfolio, risk)
    assert verdict.approved
    assert verdict.reason is None
    assert all(verdict.checks.values())
    assert verdict.metrics["risk_pct"] == pytest.approx(1.0)
    assert verdict.metrics["position_size_pct"] == pytest.approx(50.0)
    assert verdict.metrics["implied_leverage"] == pytest.approx(0.5)


# --- 1. Circuit breakers ---------------------------------------------------

def test_max_drawdown_breach_rejects(risk):
    portfolio = PortfolioState(account_equity=840_000.0, peak_equity=1_000_000.0)  # 16% DD
    verdict = evaluate_trade(make_proposal(), portfolio, risk)
    assert not verdict.approved
    assert verdict.checks == {"max_drawdown": False}
    assert "drawdown" in verdict.reason.lower()


def test_drawdown_exactly_at_limit_is_allowed(risk):
    portfolio = PortfolioState(account_equity=850_000.0, peak_equity=1_000_000.0)  # exactly 15%
    assert evaluate_trade(make_proposal(risk_amount=8_500.0, position_size=4_250.0), portfolio, risk).approved


def test_daily_loss_breaker_trips_at_limit(risk, flat_portfolio):
    flat_portfolio.daily_pnl_pct = -3.0  # limit is "> -3.0", so exactly -3.0 trips it
    verdict = evaluate_trade(make_proposal(), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_daily_loss"] is False
    assert "Daily loss" in verdict.reason


def test_weekly_loss_breaker_trips(risk, flat_portfolio):
    flat_portfolio.weekly_pnl_pct = -6.5
    verdict = evaluate_trade(make_proposal(), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_weekly_loss"] is False


def test_circuit_breaker_checked_before_proposal_itself(risk):
    """A tripped breaker rejects even a structurally broken proposal -- breakers come first."""
    portfolio = PortfolioState(account_equity=1_000_000.0, peak_equity=1_000_000.0, daily_pnl_pct=-5.0)
    verdict = evaluate_trade(make_proposal(stop_price=100.0), portfolio, risk)
    assert "mandatory_stop_loss" not in verdict.checks
    assert "Daily loss" in verdict.reason


# --- 2. Mandatory stop ---------------------------------------------------------

def test_missing_stop_rejects(risk, flat_portfolio):
    verdict = evaluate_trade(make_proposal(stop_price=100.0), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["mandatory_stop_loss"] is False


# --- 3-5. Per-trade limits -----------------------------------------------------

def test_leverage_above_1x_rejects(risk, flat_portfolio):
    verdict = evaluate_trade(make_proposal(position_size=11_000.0, risk_amount=10_000.0), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_leverage"] is False
    assert verdict.metrics["implied_leverage"] == pytest.approx(1.1)


def test_risk_per_trade_above_limit_rejects(risk, flat_portfolio):
    verdict = evaluate_trade(make_proposal(risk_amount=12_000.0), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_risk_per_trade"] is False


def test_position_size_above_cap_rejects(risk, flat_portfolio):
    # 88% notional: under 1x leverage, over the 85% position cap.
    verdict = evaluate_trade(make_proposal(position_size=8_800.0), flat_portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_position_size"] is False


# --- 6-8. Portfolio-wide limits ------------------------------------------------

def test_max_open_positions_rejects(risk):
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[
        OpenPosition("SOLUSDT", "long", 10_000.0), OpenPosition("XRPUSDT", "long", 10_000.0),
    ])
    verdict = evaluate_trade(make_proposal(), portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_open_positions"] is False


def test_portfolio_exposure_counts_existing_positions(risk):
    # 450k already open in an UNcorrelated symbol + 500k new = 95% > 90%.
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("SOLUSDT", "long", 450_000.0)])
    verdict = evaluate_trade(make_proposal(), portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_portfolio_exposure"] is False
    assert verdict.metrics["portfolio_exposure_pct"] == pytest.approx(95.0)


def test_btc_and_eth_count_as_correlated(risk):
    """
    Same total exposure as an uncorrelated pair, but BTC+ETH share a
    correlated group -- with a looser portfolio cap, only the correlated
    cap should bite.
    """
    risk.max_portfolio_exposure_pct = 200.0
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("ETHUSDT", "long", 450_000.0)])
    verdict = evaluate_trade(make_proposal(symbol="BTCUSDT"), portfolio, risk)
    assert not verdict.approved
    assert verdict.checks["max_correlated_exposure"] is False
    assert verdict.metrics["correlated_group"] == ["BTCUSDT", "ETHUSDT"]


def test_uncorrelated_existing_position_does_not_count_toward_correlated_cap(risk):
    risk.max_portfolio_exposure_pct = 200.0
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("SOLUSDT", "long", 450_000.0)])
    verdict = evaluate_trade(make_proposal(symbol="BTCUSDT"), portfolio, risk)
    assert verdict.approved
    assert verdict.metrics["correlated_exposure_pct"] == pytest.approx(50.0)


def test_zero_equity_rejects_instead_of_dividing_by_zero(risk):
    portfolio = PortfolioState(account_equity=0.0, peak_equity=0.0)
    verdict = evaluate_trade(make_proposal(), portfolio, risk)
    assert not verdict.approved
