"""
The two LIVE strategies (strategies/registry.py's STRATEGY_FOR_SYMBOL):
TrendContinuationBOS on BTC and Breakout on ETH. Covers the deterministic
per-trade math (stop, target, size, exit) and each entry/confirmation rule
on hand-built windows -- not profitability, which is what backtests are for.
"""

import pandas as pd
import pytest

from strategies.base import EntrySetup
from strategies.breakout import Breakout
from strategies.registry import STRATEGY_FOR_SYMBOL
from strategies.trend_continuation_bos import TrendContinuationBOS
from structure.market_structure import Swing, SwingType, TrendState

STRATEGIES = [TrendContinuationBOS(), Breakout()]


def _bar(**kw):
    base = dict(open=100.0, high=101.0, low=99.0, close=100.0, atr=2.0, rsi=50.0,
                ema_21=99.0, ema_50=98.0, trend_filter="bullish")
    base.update(kw)
    return base


def test_registry_assignment_is_what_the_engine_runs():
    assert isinstance(STRATEGY_FOR_SYMBOL["BTCUSDT"], TrendContinuationBOS)
    assert isinstance(STRATEGY_FOR_SYMBOL["ETHUSDT"], Breakout)


# --- Shared per-trade math (both strategies) --------------------------------

@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.name)
@pytest.mark.parametrize("direction,sign", [("long", -1), ("short", 1)])
def test_stop_is_atr_multiple_on_the_losing_side(strategy, direction, sign):
    window = pd.DataFrame([_bar(atr=2.0)])
    stop = strategy.compute_stop_loss(EntrySetup(direction, 100.0, {}), window)
    assert stop == pytest.approx(100.0 + sign * 2.0 * strategy.atr_stop_mult)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.name)
def test_target_is_reward_risk_multiple_of_stop_distance(strategy):
    long_tp = strategy.compute_take_profit(EntrySetup("long", 100.0, {}), 97.0, None)
    short_tp = strategy.compute_take_profit(EntrySetup("short", 100.0, {}), 103.0, None)
    assert long_tp == pytest.approx(100.0 + 3.0 * strategy.reward_risk)
    assert short_tp == pytest.approx(100.0 - 3.0 * strategy.reward_risk)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.name)
def test_position_size_risks_exactly_risk_amount(strategy):
    assert strategy.position_size(10_000.0, 100.0, 98.0) == pytest.approx(5_000.0)
    assert strategy.position_size(10_000.0, 100.0, 100.0) == 0.0  # no stop distance -> no size, no ZeroDivision


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.name)
class TestCheckExit:
    def test_long_stop(self, strategy):
        r = strategy.check_exit("long", 100.0, 97.0, 106.0, _bar(high=101.0, low=96.5))
        assert (r.outcome, r.exit_price, r.r_multiple) == ("loss", 97.0, -1.0)

    def test_long_target(self, strategy):
        r = strategy.check_exit("long", 100.0, 97.0, 106.0, _bar(high=106.5, low=99.0))
        assert (r.outcome, r.exit_price, r.r_multiple) == ("win", 106.0, strategy.reward_risk)

    def test_short_stop(self, strategy):
        r = strategy.check_exit("short", 100.0, 103.0, 94.0, _bar(high=103.0, low=99.0))
        assert r.outcome == "loss" and r.exit_price == 103.0

    def test_short_target(self, strategy):
        r = strategy.check_exit("short", 100.0, 103.0, 94.0, _bar(high=101.0, low=93.0))
        assert r.outcome == "win" and r.exit_price == 94.0

    def test_neither_hit_stays_open(self, strategy):
        assert strategy.check_exit("long", 100.0, 97.0, 106.0, _bar(high=105.0, low=98.0)) is None

    def test_bar_touching_both_counts_as_loss(self, strategy):
        """Conservative: on one 4H bar we can't know which came first, so assume the stop."""
        r = strategy.check_exit("long", 100.0, 97.0, 106.0, _bar(high=107.0, low=96.0))
        assert r.outcome == "loss"


# --- TrendContinuationBOS entry rules ---------------------------------------

def _tcbos_entry(signal="BOS", trend=TrendState.UPTREND, **bar):
    window = pd.DataFrame([_bar(**bar)])
    swings = [Swing(index=0, time=pd.Timestamp("2026-01-01"), price=99.0, kind=SwingType.HIGH, label="HH")]
    return TrendContinuationBOS().check_entry(window, swings, trend, signal)


def test_tcbos_long_on_bullish_bos():
    setup = _tcbos_entry(close=100.0)
    assert setup.direction == "long" and setup.entry_price == 100.0
    assert setup.diagnostics["breakout_margin_pct"] == pytest.approx((100.0 - 99.0) / 99.0 * 100)


def test_tcbos_short_on_bearish_bos():
    setup = _tcbos_entry(trend=TrendState.DOWNTREND, trend_filter="bearish", rsi=40.0)
    assert setup.direction == "short"


@pytest.mark.parametrize("kwargs", [
    dict(signal="CHoCH"),                         # needs a BOS, not a change of character
    dict(signal=None),
    dict(trend_filter="bearish"),                 # EMA cross disagrees with uptrend
    dict(rsi=80.0),                               # long into an RSI extreme
    dict(trend=TrendState.RANGE),
    dict(atr=float("nan")),                       # indicator warmup not done
])
def test_tcbos_no_entry(kwargs):
    assert _tcbos_entry(**kwargs) is None


def test_tcbos_weak_bull_requires_price_above_ema21():
    s = TrendContinuationBOS()
    assert s.confirm_entry("weak_bull_trend", {"dist_from_ema_fast_pct": 0.3})
    assert not s.confirm_entry("weak_bull_trend", {"dist_from_ema_fast_pct": -0.1})
    assert not s.confirm_entry("weak_bull_trend", {"dist_from_ema_fast_pct": None})
    assert s.confirm_entry("strong_bull_trend", {"dist_from_ema_fast_pct": -5.0})  # filter is weak_bull only


# --- Breakout entry rules ---------------------------------------------------

def _breakout_window(last_close, last_atr=3.0, n=40, rsi=60.0):
    """n-1 flat bars ranging 99-101 with ATR 2.0, then one final bar."""
    rows = [_bar(high=101.0, low=99.0, close=100.0, atr=2.0) for _ in range(n - 1)]
    rows.append(_bar(high=max(last_close, 101.0), low=min(last_close, 99.0), close=last_close, atr=last_atr, rsi=rsi))
    return pd.DataFrame(rows)


def test_breakout_long_above_prior_channel():
    setup = Breakout().check_entry(_breakout_window(102.0), [], TrendState.RANGE, None)
    assert setup.direction == "long"
    assert setup.diagnostics["breakout_margin_pct"] == pytest.approx((102.0 - 101.0) / 101.0 * 100)


def test_breakout_short_below_prior_channel():
    setup = Breakout().check_entry(_breakout_window(97.0), [], TrendState.RANGE, None)
    assert setup.direction == "short"


def test_breakout_inside_channel_is_no_entry():
    assert Breakout().check_entry(_breakout_window(100.5), [], TrendState.RANGE, None) is None


def test_breakout_needs_atr_expansion():
    # Same break, but ATR flat (ratio ~1.0 < 1.1): low conviction, skipped.
    assert Breakout().check_entry(_breakout_window(102.0, last_atr=2.0), [], TrendState.RANGE, None) is None


def test_breakout_needs_warmup_bars():
    s = Breakout()
    short = _breakout_window(102.0, n=s.channel_lookback + 14)
    assert s.check_entry(short, [], TrendState.RANGE, None) is None


def test_breakout_rejects_rsi_extremes():
    s = Breakout()
    assert s.confirm_entry("any", {"rsi_at_entry": 60.0})
    assert not s.confirm_entry("any", {"rsi_at_entry": 85.0})
    assert not s.confirm_entry("any", {"rsi_at_entry": 15.0})
