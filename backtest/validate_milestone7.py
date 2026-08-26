"""
Milestone 7 validation runner.

Runs each new strategy (breakout, pullback, mean-reversion, range trading)
against the full persisted BTCUSDT 4H history via db.repository.get_candles()
-- NOT a live OKX fetch, so this works regardless of whether OKX/VPN is up
right now (see docs/ARCHITECTURE.md's OKX ISP-block note).

Held-out validation methodology (same bar as TrendContinuationBOS's
weak_bull_trend EMA21 filter, see strategies/trend_continuation_bos.py):
run ONE full-history backtest (so every indicator has proper warmup and no
bar is re-scored with different lookback context), then split the
resulting CLOSED TRADES by entry_time into an "in-sample" group (older
than HELD_OUT_DAYS) and a "held-out" group (the most recent HELD_OUT_DAYS,
default 365 -- one year), i.e. the trades in the held-out group were never
looked at while the strategy's rules/parameters were being chosen. The
held-out group's own equity curve is replayed fresh from
starting_balance, not sliced out of the full 5yr equity curve, so its
drawdown reflects "if this were the only trading you'd done," not a
snapshot of a curve shaped by years of prior trades.

A strategy only gets called "validated" if the held-out group shows a
genuine positive expectancy -- not just a positive full-period number
propped up by an in-sample-only edge. Anything that fails this is
reported honestly as NOT validated, same as weak_bull_trend was reported
as "reduced, not cured" rather than forced into a clean success story.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta

from config.config import RISK, BACKTEST, MARKET
from db.session import get_session
from db.repository import get_candles, get_or_create_asset
from backtest.backtest_engine import run_backtest, BacktestResult
from strategies.base import Strategy

HELD_OUT_DAYS = 365
SYMBOL = "BTCUSDT"


def _held_out_split(full_result: BacktestResult, cutoff, starting_balance: float):
    """
    Splits full_result's CLOSED trades by entry_time into (in_sample,
    held_out) BacktestResults. Each gets its own equity curve replayed
    fresh from starting_balance over just its own trades, in order -- see
    module docstring for why this isn't a slice of the full curve.
    """
    in_sample = BacktestResult()
    held_out = BacktestResult()

    balance_in = starting_balance
    balance_out = starting_balance

    for t in full_result.trades:
        if t.entry_time < cutoff:
            in_sample.trades.append(t)
            balance_in += t.risk_amount * t.r_multiple
            in_sample.equity_curve.append(balance_in)
        else:
            held_out.trades.append(t)
            balance_out += t.risk_amount * t.r_multiple
            held_out.equity_curve.append(balance_out)

    return in_sample, held_out


def validate(strategy: Strategy, df) -> dict:
    full_result = run_backtest(df, strategy, RISK, SYMBOL, starting_balance=BACKTEST.starting_balance)
    cutoff = df["open_time"].max() - timedelta(days=HELD_OUT_DAYS)
    in_sample, held_out = _held_out_split(full_result, cutoff, BACKTEST.starting_balance)

    full_summary = full_result.summary()
    in_sample_summary = in_sample.summary()
    held_out_summary = held_out.summary()
    regime_breakdown = full_result.by_regime()

    validated = held_out_summary["total_trades"] >= 5 and held_out_summary["expectancy_r"] > 0

    return {
        "strategy": strategy.name,
        "full_period": full_summary,
        "in_sample": in_sample_summary,
        "held_out": held_out_summary,
        "held_out_cutoff": cutoff,
        "regime_breakdown": regime_breakdown,
        "validated": validated,
    }


def print_report(result: dict) -> None:
    print(f"\n{'=' * 70}\n{result['strategy']}\n{'=' * 70}")
    print(f"Held-out cutoff (most recent {HELD_OUT_DAYS}d, NOT used to design the strategy): "
          f"{result['held_out_cutoff']}")

    print("\nFull period (5yr):")
    for k, v in result["full_period"].items():
        print(f"  {k}: {v}")

    print(f"\nIn-sample (before cutoff):")
    for k, v in result["in_sample"].items():
        print(f"  {k}: {v}")

    print(f"\nHeld-out (last {HELD_OUT_DAYS}d, genuine out-of-sample):")
    for k, v in result["held_out"].items():
        print(f"  {k}: {v}")

    print("\nRegime breakdown (full period):")
    for regime, stats in sorted(result["regime_breakdown"].items(), key=lambda kv: kv[1]["expectancy_r"], reverse=True):
        print(f"  {regime:<20}{stats['trades']:>6} trades  win_rate={stats['win_rate_pct']:>5.1f}%  expectancy={stats['expectancy_r']:>+.3f}R")

    verdict = "VALIDATED (positive held-out expectancy, n>=5)" if result["validated"] else "NOT VALIDATED"
    print(f"\nVerdict: {verdict}")
    if result["held_out"]["total_trades"] < 5:
        print(f"  NOTE: held-out sample is only {result['held_out']['total_trades']} trades -- "
              f"too small to trust the magnitude even if the sign looks good/bad.")


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from strategies.breakout import Breakout

    with get_session() as session:
        asset = get_or_create_asset(session, SYMBOL, exchange=MARKET.exchange, category=MARKET.category)
        df = get_candles(session, asset, MARKET.primary_timeframe, source="okx")

    print(f"Loaded {len(df)} persisted candles: {df['open_time'].min()} -> {df['open_time'].max()}")

    result = validate(Breakout(), df)
    print_report(result)
