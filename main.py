"""
Phase 1 demo entrypoint.

Pulls historical data, runs the structure engine, regime classifier, and
backtest, then checks the current bar for a live trade proposal. Prints
everything to console — no execution happens here.

NOTE: Bybit's public API is geo-blocked from this machine (HTTP 403
CloudFront), and Binance is also blocked (HTTP 451). This script uses
data/okx_client.py (OKX public API, same interface as BybitClient) as a
drop-in substitute for BACKTESTING purposes only. Bybit remains the
documented execution exchange per docs/ARCHITECTURE.md — swap back to
BybitClient once execution/testnet work begins from a machine with
Bybit access.
"""

import sys

# Windows' console defaults stdout/stderr to the system codepage (cp1252 on
# this machine), which can't encode characters this project actually uses on
# purpose (the Naira sign, U+20A6, in reporting/plain_language_summary.py —
# NGN amounts are the whole point, not decoration). Force UTF-8 so console
# output matches what's actually being generated instead of crashing on it.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config.config import MARKET, RISK, BACKTEST
from data.okx_client import OKXClient
from backtest.backtest_engine import run_backtest
from strategies.registry import STRATEGY_FOR_SYMBOL, strategy_parameters
from proposals.trade_proposal import build_proposal
from reporting.plain_language_summary import full_report
from db.session import get_session
from db.repository import (
    build_portfolio_state, get_or_create_asset, save_backtest_run, save_backtest_trades, save_candles, save_signal,
)
from risk.risk_engine import evaluate_trade

DATA_SOURCE = "okx"  # see NOTE above — Bybit is the documented execution exchange


def run_for_symbol(symbol: str):
    print(f"\n{'=' * 60}\n{symbol}\n{'=' * 60}")

    client = OKXClient(testnet=False, category=MARKET.category)
    df = client.get_historical_klines(symbol, MARKET.primary_timeframe, days=BACKTEST.history_days)

    if df.empty:
        print("No data returned. Check network access / symbol / category.")
        return

    print(f"Fetched {len(df)} candles ({df['open_time'].min()} -> {df['open_time'].max()})")

    with get_session() as session:
        asset = get_or_create_asset(session, symbol, exchange=MARKET.exchange, category=MARKET.category)
        new_candles = save_candles(session, asset, MARKET.primary_timeframe, DATA_SOURCE, df)
    print(f"Persisted {new_candles} new candles to Postgres (existing rows skipped).")

    strategy = STRATEGY_FOR_SYMBOL[symbol]

    bt = run_backtest(
        df, strategy, RISK, symbol,
        starting_balance=BACKTEST.starting_balance,
    )
    summary = bt.summary()
    print(f"\nBacktest results ({strategy.name} setup):")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    regime_breakdown = bt.by_regime()
    print("\nRegime breakdown:")
    print(f"  {'regime':<20}{'trades':>8}{'win_rate':>10}{'expectancy_r':>14}")
    for regime, stats in sorted(regime_breakdown.items(), key=lambda kv: kv[1]['expectancy_r'], reverse=True):
        print(f"  {regime:<20}{stats['trades']:>8}{stats['win_rate_pct']:>9.1f}%{stats['expectancy_r']:>14.3f}")

    with get_session() as session:
        asset = get_or_create_asset(session, symbol, exchange=MARKET.exchange, category=MARKET.category)
        run = save_backtest_run(
            session, asset, MARKET.primary_timeframe, DATA_SOURCE, df,
            params={
                "strategy": strategy.name,
                "risk_per_trade_pct": RISK.risk_per_trade_pct,
                "max_position_size_pct": RISK.max_position_size_pct,
                "starting_balance": BACKTEST.starting_balance,
                # Per-strategy params from the same helper strategies/registry.py
                # uses for the frontend Strategies page -- one source of truth
                # for "what are this strategy's actual instantiated parameters,"
                # not duplicated/hardcoded per-strategy here.
                **strategy_parameters(strategy),
            },
        )
        n_trades = save_backtest_trades(session, run, bt.trades)
    print(f"Persisted backtest_run id={run.id} with {n_trades} trades to Postgres.")

    # Real portfolio state as of Milestone 4 — build_portfolio_state()
    # queries actual paper_trades rows (open positions, realized P&L,
    # drawdown). It legitimately comes back empty/at-rest until the first
    # paper trade closes; that's real absence of history, not a stub
    # standing in for missing data (see risk/risk_engine.py). Built BEFORE
    # the proposal now, since build_proposal()'s sizing needs it too (same
    # portfolio object used for both sizing and the risk engine verdict).
    with get_session() as session:
        portfolio = build_portfolio_state(session, account_baseline=RISK.account_size_ngn)

    proposal = build_proposal(
        df, symbol, strategy=strategy, risk_config=RISK, portfolio=portfolio,
        backtest_summary=summary,
    )

    print("\nCurrent trade proposal:")
    if proposal is None:
        print("  No valid setup right now. The bot does not force a trade to exist.")
    else:
        for k, v in proposal.as_dict().items():
            print(f"  {k}: {v}")

        verdict = evaluate_trade(proposal, portfolio, RISK)

        print(f"\nRisk engine verdict: {'APPROVED' if verdict.approved else 'REJECTED'}")
        if verdict.reason:
            print(f"  Reason: {verdict.reason}")

        with get_session() as session:
            asset = get_or_create_asset(session, symbol, exchange=MARKET.exchange, category=MARKET.category)
            signal = save_signal(session, asset, proposal, verdict, triggering_candle_time=df.iloc[-1]["open_time"])
        print(f"Persisted signal id={signal.id} (status={signal.status.value}) to Postgres.")

    print("\nPlain-language summary:")
    print(full_report(summary, regime_breakdown=regime_breakdown, proposal=proposal, symbol=symbol))


if __name__ == "__main__":
    for sym in MARKET.pairs:
        run_for_symbol(sym)
