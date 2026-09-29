"""
risk/position_sizing.py's size_position(): sizes DOWN to the tightest of
three notional caps, never UP past the risk-based size, never rejects.
"""

import pytest

from risk.position_sizing import OpenPosition, PortfolioState, correlated_group, size_position

GROUPS = [["BTCUSDT", "ETHUSDT"]]


def _size(risk_based_size, portfolio, entry=100.0, stop=98.0, symbol="BTCUSDT", pos=85.0, port=90.0, corr=90.0):
    return size_position(risk_based_size, entry, stop, symbol, portfolio, pos, port, corr, GROUPS)


def test_risk_based_size_used_when_under_every_cap(flat_portfolio):
    r = _size(5_000.0, flat_portfolio)  # 500k notional, well under 850k
    assert r.position_size == 5_000.0
    assert r.risk_amount == pytest.approx(10_000.0)
    assert not r.was_capped
    assert r.binding_constraint == "risk_based"


def test_sizes_down_to_position_cap_and_risks_less(flat_portfolio):
    r = _size(10_000.0, flat_portfolio)  # 1,000k notional wanted, cap is 850k
    assert r.was_capped
    assert r.binding_constraint == "position_cap"
    assert r.position_size == pytest.approx(8_500.0)
    assert r.risk_amount == pytest.approx(17_000.0)  # 8,500 units x 2 pt stop


def test_portfolio_cap_binds_when_other_positions_open():
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("SOLUSDT", "long", 600_000.0)])
    r = _size(5_000.0, portfolio)  # room left: 900k - 600k = 300k -> 3,000 units
    assert r.binding_constraint == "portfolio_cap"
    assert r.position_size == pytest.approx(3_000.0)


def test_correlated_cap_binds_before_portfolio_cap():
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("ETHUSDT", "long", 600_000.0)])
    r = _size(5_000.0, portfolio, port=200.0)  # correlated room: 900k - 600k = 300k
    assert r.binding_constraint == "correlated_cap"
    assert r.position_size == pytest.approx(3_000.0)


def test_no_room_left_sizes_to_zero_not_negative():
    portfolio = PortfolioState(1_000_000.0, 1_000_000.0, open_positions=[OpenPosition("ETHUSDT", "long", 950_000.0)])
    r = _size(5_000.0, portfolio)
    assert r.position_size == 0.0
    assert r.risk_amount == 0.0
    assert r.was_capped


def test_never_sizes_up_past_risk_based_size(flat_portfolio):
    r = _size(1.0, flat_portfolio)
    assert r.position_size == 1.0


def test_short_stop_distance_is_absolute(flat_portfolio):
    r = _size(5_000.0, flat_portfolio, entry=100.0, stop=102.0)
    assert r.risk_amount == pytest.approx(10_000.0)


def test_correlated_group_lookup():
    assert correlated_group("ETHUSDT", GROUPS) == ["BTCUSDT", "ETHUSDT"]
    assert correlated_group("SOLUSDT", GROUPS) == ["SOLUSDT"]
