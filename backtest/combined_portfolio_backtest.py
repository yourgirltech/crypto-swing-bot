"""
Combined portfolio backtest: TrendContinuationBOS-on-BTCUSDT running
CONCURRENTLY with Breakout-on-ETHUSDT, as one real portfolio (one shared
account balance, both positions tracked simultaneously, sized against
each other) -- not two independent single-asset backtests summed after
the fact.

Why this exists: every backtest run so far (backtest_engine.run_backtest())
tracks exactly ONE open position at a time (`in_trade: bool`, one `Trade`
slot) -- structurally incapable of representing two assets' positions
overlapping in time. Before treating "Breakout validates on ETH" as a
"safe to go live in paper trading" conclusion, the actual scenario that
matters for risk management -- both positions open at once -- had never
been backtested, only proven safe for each asset IN ISOLATION. This
script is that missing test.

Mechanics, deliberately mirroring backtest_engine.run_backtest()'s
existing pattern (same SwingTracker/classify_trend/classify_regime calls,
same size_position() call, same no-lookahead windowing) but interleaved
across BOTH assets on ONE shared timeline and ONE shared balance:
- BTC and ETH candles are restricted to their common timestamps (10,950
  of 10,958 BTC bars overlap with ETH's full history -- ETH started
  persisting 2 days later; the 8 BTC-only bars at the very start are
  dropped so both walks start from identical, aligned bars).
- At each shared timestep: check exits for whichever position(s) are
  open first (settling realized P&L into the ONE shared balance
  immediately), THEN check entries for whichever asset has no open
  position, sizing against the REAL current PortfolioState -- which, for
  the first time, can actually contain the OTHER asset's still-open
  position. This is the exact mechanism (risk.position_sizing.size_position())
  that has only ever been exercised against an empty book until now.
- Like backtest_engine.run_backtest(), this calls size_position()
  directly, NOT risk_engine.evaluate_trade() -- consistent with the
  existing single-asset backtest's own precedent (backtests test what
  WOULD be sized, not the live accept/reject gate).

Two runs are provided:
- `run(portfolio_cap_pct=RISK.max_portfolio_exposure_pct, correlated_cap_pct=RISK.max_correlated_exposure_pct)`
  -- CURRENT config values, to check whether going live today would ever
  actually hit those caps.
- `run(portfolio_cap_pct=1000.0, correlated_cap_pct=1000.0)` -- effectively
  uncapped, to observe the NATURAL combined-notional distribution the
  same way max_position_size_pct was originally derived (Milestone 4):
  run uncapped, observe where real trades cluster, find the gap that
  makes a good cap threshold, don't guess.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import List, Optional

from config.config import RISK, BACKTEST, MARKET
from db.session import get_session
from db.repository import get_candles, get_or_create_asset
from indicators.indicators import add_all_indicators
from structure.market_structure import SwingTracker, label_swing_sequence, classify_trend, detect_bos_choch
from regime.regime_classifier import classify_regime
from strategies.trend_continuation_bos import TrendContinuationBOS
from strategies.breakout import Breakout
from risk.position_sizing import OpenPosition, PortfolioState, size_position


@dataclass
class CombinedTrade:
    symbol: str
    strategy: str
    entry_time: object
    entry_price: float
    stop_price: float
    target_price: float
    position_size: float
    notional: float
    risk_amount: float
    was_capped: bool
    binding_constraint: str
    concurrent_with: Optional[str]  # the OTHER symbol, if it was open at entry time, else None
    exit_time: object = None
    exit_price: float = None
    outcome: str = None
    r_multiple: float = None


@dataclass
class ConcurrentEntry:
    """
    Recorded at the EXACT moment a second position is sized while another
    is already open -- the real, precise data point this whole script
    exists to produce (not inferred after the fact from a bar-by-bar
    "both open" scan, which would be off by one bar relative to the
    actual sizing decision).
    """
    time: object
    entering_symbol: str
    already_open_symbol: str
    already_open_notional: float
    new_notional: float
    combined_notional_pct: float
    equity_at_time: float
    binding_constraint: str


def _load_aligned(symbol_a: str, symbol_b: str):
    with get_session() as session:
        asset_a = get_or_create_asset(session, symbol_a, exchange=MARKET.exchange, category=MARKET.category)
        asset_b = get_or_create_asset(session, symbol_b, exchange=MARKET.exchange, category=MARKET.category)
        df_a = get_candles(session, asset_a, MARKET.primary_timeframe, source="okx")
        df_b = get_candles(session, asset_b, MARKET.primary_timeframe, source="okx")

    common = sorted(set(df_a["open_time"]) & set(df_b["open_time"]))
    df_a = df_a[df_a["open_time"].isin(common)].sort_values("open_time").reset_index(drop=True)
    df_b = df_b[df_b["open_time"].isin(common)].sort_values("open_time").reset_index(drop=True)
    assert (df_a["open_time"].values == df_b["open_time"].values).all(), "timestamp alignment failed"

    df_a = add_all_indicators(df_a, ema_fast=21, ema_slow=50, rsi_period=14, atr_period=14)
    df_b = add_all_indicators(df_b, ema_fast=21, ema_slow=50, rsi_period=14, atr_period=14)
    return df_a, df_b


def _try_entry(symbol, strategy, df, i, tracker, balance, portfolio, portfolio_cap_pct, correlated_cap_pct):
    window = df.iloc[:i + 1]
    swings = tracker.update(window)
    swings = label_swing_sequence(swings)
    trend_state = classify_trend(swings)
    signal = detect_bos_choch(swings, trend_state)

    setup = strategy.check_entry(window, swings, trend_state, signal)
    if setup is None:
        return None

    regime_info = classify_regime(window, ema_fast_col="ema_21", ema_slow_col="ema_50")
    if not strategy.confirm_entry(regime_info["regime"], setup.diagnostics):
        return None
    if strategy.check_invalidation(setup, window):
        return None

    stop = strategy.compute_stop_loss(setup, window)
    target = strategy.compute_take_profit(setup, stop, window)

    risk_amount_target = balance * (RISK.risk_per_trade_pct / 100)
    raw_size = strategy.position_size(risk_amount_target, setup.entry_price, stop)
    sizing = size_position(
        raw_size, setup.entry_price, stop, symbol, portfolio,
        RISK.max_position_size_pct, portfolio_cap_pct, correlated_cap_pct, RISK.correlated_groups,
    )
    if sizing.position_size <= 0:
        return None

    notional = sizing.position_size * setup.entry_price
    return {
        "direction": setup.direction, "entry_price": setup.entry_price,
        "stop": stop, "target": target,
        "position_size": sizing.position_size, "risk_amount": sizing.risk_amount,
        "notional": notional, "was_capped": sizing.was_capped,
        "binding_constraint": sizing.binding_constraint,
    }


def run(portfolio_cap_pct: float, correlated_cap_pct: float) -> dict:
    df_btc, df_eth = _load_aligned("BTCUSDT", "ETHUSDT")
    btc_strategy = TrendContinuationBOS()
    eth_strategy = Breakout()
    btc_tracker = SwingTracker(lookback=btc_strategy.swing_lookback)
    eth_tracker = SwingTracker(lookback=eth_strategy.swing_lookback)

    balance = BACKTEST.starting_balance
    peak_equity = balance
    btc_open, eth_open = None, None
    trades: List[CombinedTrade] = []
    concurrent_entries: List[ConcurrentEntry] = []

    min_bars = 60
    n = len(df_btc)

    for i in range(min_bars, n):
        btc_bar = df_btc.iloc[i]
        eth_bar = df_eth.iloc[i]
        now = btc_bar["open_time"]

        # 1. Exits first -- settle realized P&L into the ONE shared balance
        # before this bar's entry decisions use it.
        if btc_open is not None:
            exit_result = btc_strategy.check_exit(
                btc_open["direction"], btc_open["entry_price"], btc_open["stop"], btc_open["target"], btc_bar
            )
            if exit_result is not None:
                balance += btc_open["risk_amount"] * exit_result.r_multiple
                peak_equity = max(peak_equity, balance)
                trade = btc_open["trade"]
                trade.exit_time, trade.exit_price = now, exit_result.exit_price
                trade.outcome, trade.r_multiple = exit_result.outcome, exit_result.r_multiple
                btc_open = None

        if eth_open is not None:
            exit_result = eth_strategy.check_exit(
                eth_open["direction"], eth_open["entry_price"], eth_open["stop"], eth_open["target"], eth_bar
            )
            if exit_result is not None:
                balance += eth_open["risk_amount"] * exit_result.r_multiple
                peak_equity = max(peak_equity, balance)
                trade = eth_open["trade"]
                trade.exit_time, trade.exit_price = now, exit_result.exit_price
                trade.outcome, trade.r_multiple = exit_result.outcome, exit_result.r_multiple
                eth_open = None

        # 2. Entries -- against the REAL current portfolio state, which may
        # already contain the OTHER asset's open position.
        current_positions = []
        if btc_open is not None:
            current_positions.append(OpenPosition("BTCUSDT", btc_open["direction"], btc_open["notional"]))
        if eth_open is not None:
            current_positions.append(OpenPosition("ETHUSDT", eth_open["direction"], eth_open["notional"]))
        portfolio = PortfolioState(account_equity=balance, peak_equity=peak_equity, open_positions=current_positions)

        if btc_open is None:
            result = _try_entry("BTCUSDT", btc_strategy, df_btc, i, btc_tracker, balance, portfolio,
                                 portfolio_cap_pct, correlated_cap_pct)
            if result is not None:
                trade = CombinedTrade(
                    symbol="BTCUSDT", strategy=btc_strategy.name, entry_time=now,
                    entry_price=result["entry_price"], stop_price=result["stop"], target_price=result["target"],
                    position_size=result["position_size"], notional=result["notional"], risk_amount=result["risk_amount"],
                    was_capped=result["was_capped"], binding_constraint=result["binding_constraint"],
                    concurrent_with="ETHUSDT" if eth_open is not None else None,
                )
                trades.append(trade)
                if eth_open is not None:
                    combined_notional = eth_open["notional"] + result["notional"]
                    concurrent_entries.append(ConcurrentEntry(
                        time=now, entering_symbol="BTCUSDT", already_open_symbol="ETHUSDT",
                        already_open_notional=eth_open["notional"], new_notional=result["notional"],
                        combined_notional_pct=combined_notional / balance * 100,
                        equity_at_time=balance, binding_constraint=result["binding_constraint"],
                    ))
                btc_open = {**result, "trade": trade}

        if eth_open is None:
            # Refresh portfolio to include a same-bar BTC entry just opened above.
            current_positions = []
            if btc_open is not None:
                current_positions.append(OpenPosition("BTCUSDT", btc_open["direction"], btc_open["notional"]))
            portfolio = PortfolioState(account_equity=balance, peak_equity=peak_equity, open_positions=current_positions)
            result = _try_entry("ETHUSDT", eth_strategy, df_eth, i, eth_tracker, balance, portfolio,
                                 portfolio_cap_pct, correlated_cap_pct)
            if result is not None:
                trade = CombinedTrade(
                    symbol="ETHUSDT", strategy=eth_strategy.name, entry_time=now,
                    entry_price=result["entry_price"], stop_price=result["stop"], target_price=result["target"],
                    position_size=result["position_size"], notional=result["notional"], risk_amount=result["risk_amount"],
                    was_capped=result["was_capped"], binding_constraint=result["binding_constraint"],
                    concurrent_with="BTCUSDT" if btc_open is not None else None,
                )
                if btc_open is not None:
                    combined_notional = btc_open["notional"] + result["notional"]
                    concurrent_entries.append(ConcurrentEntry(
                        time=now, entering_symbol="ETHUSDT", already_open_symbol="BTCUSDT",
                        already_open_notional=btc_open["notional"], new_notional=result["notional"],
                        combined_notional_pct=combined_notional / balance * 100,
                        equity_at_time=balance, binding_constraint=result["binding_constraint"],
                    ))
                trades.append(trade)
                eth_open = {**result, "trade": trade}

    closed = [t for t in trades if t.outcome is not None]
    return {
        "final_balance": balance,
        "total_trades": len(closed),
        "btc_trades": len([t for t in closed if t.symbol == "BTCUSDT"]),
        "eth_trades": len([t for t in closed if t.symbol == "ETHUSDT"]),
        "concurrent_entries": concurrent_entries,
        "trades": trades,
    }


def _print_run(label: str, result: dict) -> None:
    print("=" * 70)
    print(label)
    print("=" * 70)
    print(f"Final balance: {result['final_balance']:,.0f} (started {BACKTEST.starting_balance:,.0f})")
    print(f"Total closed trades: {result['total_trades']} (BTC {result['btc_trades']}, ETH {result['eth_trades']})")
    entries = result["concurrent_entries"]
    print(f"Concurrent entries (opened while the OTHER asset's position was already live): {len(entries)}")
    if entries:
        pcts = sorted(e.combined_notional_pct for e in entries)
        print("Combined notional %% at each concurrent entry (sorted):")
        for e in sorted(entries, key=lambda e: e.combined_notional_pct):
            print(f"  {e.time}  entering={e.entering_symbol:<8} already_open={e.already_open_symbol:<8} "
                  f"combined={e.combined_notional_pct:6.2f}%  bound_by={e.binding_constraint}")
        print(f"  max: {max(pcts):.2f}%  min: {min(pcts):.2f}%  median: {pcts[len(pcts)//2]:.2f}%")
    capped = [t for t in result["trades"] if t.binding_constraint in ("portfolio_cap", "correlated_cap")]
    print(f"Trades where portfolio_cap/correlated_cap actually bound sizing: {len(capped)}")
    for t in capped:
        print(f"  {t.symbol} {t.entry_time} bound by {t.binding_constraint}, notional={t.notional:,.0f}")
    print()


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result_capped = run(RISK.max_portfolio_exposure_pct, RISK.max_correlated_exposure_pct)
    _print_run(
        f"RUN 1: current config caps (max_portfolio_exposure_pct={RISK.max_portfolio_exposure_pct}%, "
        f"max_correlated_exposure_pct={RISK.max_correlated_exposure_pct}%)",
        result_capped,
    )

    result_uncapped = run(1000.0, 1000.0)
    _print_run(
        "RUN 2: portfolio/correlated caps effectively uncapped (1000%) -- "
        "observe the NATURAL combined-notional distribution",
        result_uncapped,
    )
