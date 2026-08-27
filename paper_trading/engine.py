"""
Paper trading engine -- Milestone 4.

A standing, manually-run loop (not a one-shot script like main.py): poll
OKX for the latest closed candle, and either (a) monitor an already-open
paper position for a stop/target hit, or (b) scan for a new entry signal.

Design decision confirmed with the user 2026-08-25: paper trades require
EXPLICIT HUMAN APPROVAL, exactly like live trading will -- there is no
auto-execute mode. The goal is to build the actual human-approval habit
and workflow now, not just simulate fills faster. A risk-engine-APPROVED
proposal is never auto-opened; it's shown as a full plain-language review
(reporting.plain_language_summary.explain_full_trade_review) and the loop
blocks on a real y/n before doing anything. A risk-engine-REJECTED
proposal is logged with its reason and never even reaches a human -- there
is nothing to approve.

Price feed decision (confirmed with the user 2026-08-25): REST POLLING
ONLY, not WebSocket. Entries only ever trigger on a CLOSED 4H candle
anyway (strategy.check_entry), so real-time ticks add nothing there; and
checking stop/target against the same closed-candle high/low the backtest
was validated against (strategy.check_exit) keeps paper trading a fair
like-for-like test of what was actually backtested, rather than testing a
finer-grained behavior the backtest never validated. The cost -- up to
~4h of delay finding out a stop/target was hit -- has zero real
consequence in paper trading, since no real capital is exposed during
that delay. REVISIT at the live-trading milestone (Milestone 12), where a
real-time reaction actually reduces real risk.
"""

import sys

# Same fix as main.py: Windows' console defaults stdout/stderr to the
# system codepage (cp1252 here), which can't encode the Naira sign
# (U+20A6) this project prints on purpose (see reporting/plain_language_
# summary.py). This is its own process entrypoint, so it needs the same
# fix independently -- it does not inherit main.py's.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
from datetime import datetime, timedelta, timezone

from config.config import BACKTEST, MARKET, RISK
from data.okx_client import OKXClient
from backtest.backtest_engine import run_backtest
from strategies.base import Strategy
from strategies.registry import STRATEGY_FOR_SYMBOL
from proposals.trade_proposal import build_proposal
from reporting.plain_language_summary import explain_full_trade_review
from risk.risk_engine import evaluate_trade
from db.session import get_session
from db.models import Asset, HumanDecision, PaperTrade, Signal
from db.repository import (
    build_portfolio_state, close_paper_trade, create_paper_trade,
    get_open_paper_trade, get_or_create_asset, has_signal_for_candle,
    record_derivatives_snapshot, record_heartbeat, record_human_decision, save_candles, save_signal,
)

DATA_SOURCE = "okx"
ENGINE_NAME = "paper_trading"  # db.models.EngineHeartbeat.engine_name -- see System Health page
POLL_INTERVAL_SECONDS = 900  # 15 min -- see module docstring for why polling, not WebSocket
HISTORY_DAYS = 120  # plenty of warmup for indicators/structure; cheap to refetch each poll via OKXClient's existing retry logic
REFERENCE_BACKTEST_REFRESH = timedelta(hours=24)  # how often to refresh the backtested-stats context below

# Per-symbol-strategy mapping now lives in strategies/registry.py (the
# single source of truth also used by the frontend Strategies page via
# api/routes/strategies.py, and by main.py) -- imported here, not
# redefined, so the live engine can never drift from what the registry
# and main.py say a symbol's strategy is.

# Cache of {(symbol, strategy.name): (summary, regime_breakdown,
# last_refreshed_at)} -- see _get_reference_stats(). Keyed by (symbol,
# strategy) rather than symbol alone: a cache keyed by symbol only would
# silently return the WRONG strategy's backtested stats if the same
# symbol were ever evaluated under two different strategies (not the
# case today -- one strategy per symbol -- but a real correctness trap
# once STRATEGY_FOR_SYMBOL exists as a real mapping rather than a single
# hardcoded strategy). A live proposal needs the FULL backtested history
# (BACKTEST.history_days, ~5yr) to show a real win rate/expectancy/sample
# size, which is far more data than the ~120-day window HISTORY_DAYS fetches
# for indicator/structure warmup on every poll -- refetching 5yr of candles
# every 15 minutes just to re-derive the same stats would be wasteful, so
# this is computed once at startup and refreshed on REFERENCE_BACKTEST_REFRESH.
_reference_stats_cache: dict = {}


def _apply_slippage(price: float, side: str, slippage_pct: float) -> float:
    """
    side: the actual order side being filled ("buy" or "sell"). Slippage
    always moves the fill AGAINST the trader -- a buy fills higher, a sell
    fills lower than the reference price -- regardless of long/short or
    entry/exit, which is the standard conservative assumption.
    """
    adj = price * (slippage_pct / 100)
    return price + adj if side == "buy" else price - adj


def _fee(notional: float, fee_pct: float) -> float:
    return notional * (fee_pct / 100)


def _entry_side(direction: str) -> str:
    return "buy" if direction == "long" else "sell"


def _exit_side(direction: str) -> str:
    return "sell" if direction == "long" else "buy"


def _get_reference_stats(symbol: str, strategy) -> tuple:
    """
    Returns (backtest_summary, regime_breakdown) for `symbol`, running a
    fresh full-history backtest at most once every REFERENCE_BACKTEST_REFRESH
    (and always on first call). This is what lets a live proposal show a
    real "backtested win rate/expectancy/sample size for this exact setup
    type" instead of always coming back empty.
    """
    cache_key = (symbol, strategy.name)
    cached = _reference_stats_cache.get(cache_key)
    if cached is not None and datetime.now(timezone.utc) - cached[2] < REFERENCE_BACKTEST_REFRESH:
        return cached[0], cached[1]

    print(f"[{symbol}] Refreshing reference backtest ({BACKTEST.history_days} days, {strategy.name}) for backtested-stats context...")
    client = OKXClient(testnet=False, category=MARKET.category)
    df = client.get_historical_klines(symbol, MARKET.primary_timeframe, days=BACKTEST.history_days)
    bt = run_backtest(df, strategy, RISK, symbol, starting_balance=BACKTEST.starting_balance)
    summary, regime_breakdown = bt.summary(), bt.by_regime()
    _reference_stats_cache[cache_key] = (summary, regime_breakdown, datetime.now(timezone.utc))
    return summary, regime_breakdown


def _collect_derivatives_snapshot(symbol: str) -> None:
    """
    Milestone 9 (DEFERRED as a live feature -- see docs/ARCHITECTURE.md's
    "Milestone 9 -- DEFERRED" section). PASSIVE COLLECTION ONLY: not read
    by any strategy, risk engine, or dashboard page today. Wrapped in its
    own try/except so a failure here (or a partial one -- each of the
    three OKX calls independently returns None on its own failure, see
    OKXClient.get_funding_rate/get_open_interest/get_long_short_ratio)
    can NEVER affect the actual trading poll cycle that follows -- same
    principle as okx_client.py's _log_retry_event.
    """
    try:
        client = OKXClient(testnet=False, category=MARKET.category)
        funding_rate = client.get_funding_rate(symbol)
        open_interest = client.get_open_interest(symbol)
        long_short_ratio = client.get_long_short_ratio(symbol)
        with get_session() as session:
            record_derivatives_snapshot(
                session, symbol, funding_rate, open_interest, long_short_ratio, source=DATA_SOURCE,
            )
    except Exception as e:
        print(f"[{symbol}] Derivatives snapshot collection failed (non-critical, skipped this cycle): {e!r}")


def run_once(symbol: str, strategy: Strategy) -> None:
    # Recorded FIRST, before any fetch/logic -- proof of liveness for the
    # System Health page even if this cycle later raises. A cycle that
    # errors out still proves the process was alive and attempting work
    # at this timestamp, which is the actual thing "is it running" asks.
    with get_session() as session:
        record_heartbeat(session, ENGINE_NAME, symbol=symbol, detail="poll cycle started")

    _collect_derivatives_snapshot(symbol)

    backtest_summary, regime_breakdown = _get_reference_stats(symbol, strategy)

    client = OKXClient(testnet=False, category=MARKET.category)
    df = client.get_historical_klines(symbol, MARKET.primary_timeframe, days=HISTORY_DAYS)

    if df.empty:
        print(f"[{symbol}] No data returned this poll cycle. Check network access.")
        return

    latest_candle_time = df.iloc[-1]["open_time"]
    latest_bar = df.iloc[-1]

    with get_session() as session:
        asset = get_or_create_asset(session, symbol, exchange=MARKET.exchange, category=MARKET.category)
        save_candles(session, asset, MARKET.primary_timeframe, DATA_SOURCE, df)
        asset_id = asset.id
        open_trade_id = getattr(get_open_paper_trade(session, asset), "id", None)

    if open_trade_id is not None:
        _check_open_position(symbol, open_trade_id, strategy, latest_bar, latest_candle_time)
        return

    _check_for_entry(symbol, asset_id, strategy, df, latest_candle_time, backtest_summary, regime_breakdown)


def _check_open_position(symbol: str, open_trade_id: int, strategy, latest_bar, latest_candle_time) -> None:
    with get_session() as session:
        open_trade = session.get(PaperTrade, open_trade_id)
        direction, stop_price, target_price = open_trade.direction, open_trade.stop_price, open_trade.target_price
        proposed_entry_price = open_trade.proposed_entry_price
        entry_fill_price, entry_fee = open_trade.entry_fill_price, open_trade.entry_fee
        position_size, risk_amount = open_trade.position_size, open_trade.risk_amount

    # proposed_entry_price (pre-slippage), not entry_fill_price -- check_exit's
    # r_multiple is the "ideal" backtest-style figure (see the print below),
    # matching backtest_engine.Trade.entry_price's same pre-slippage semantics.
    # The REALISTIC r_multiple (post-slippage/fees) is computed separately
    # below from entry_fill_price/exit_fill_price, same as before this change.
    exit_result = strategy.check_exit(direction, proposed_entry_price, stop_price, target_price, latest_bar)
    if exit_result is None:
        print(f"[{symbol}] Paper trade #{open_trade_id} still open ({direction}, entry {entry_fill_price:.2f}). "
              f"No stop/target hit on latest closed candle ({latest_candle_time}).")
        return

    side = _exit_side(direction)
    exit_fill_price = _apply_slippage(exit_result.exit_price, side, BACKTEST.slippage_pct)
    exit_fee = _fee(position_size * exit_fill_price, BACKTEST.fee_pct)

    direction_sign = 1 if direction == "long" else -1
    pnl_ngn = (exit_fill_price - entry_fill_price) * position_size * direction_sign - entry_fee - exit_fee
    r_multiple_realistic = pnl_ngn / risk_amount if risk_amount else 0.0

    with get_session() as session:
        open_trade = session.get(PaperTrade, open_trade_id)
        close_paper_trade(
            session, open_trade, exit_result, exit_fill_price, exit_fee,
            latest_candle_time, r_multiple_realistic, pnl_ngn,
        )

    print(
        f"[{symbol}] Paper trade #{open_trade_id} CLOSED: {exit_result.outcome.upper()} at "
        f"{exit_fill_price:.2f} (proposed {exit_result.exit_price:.2f}). "
        f"Ideal R (backtest-style): {exit_result.r_multiple:+.2f}. "
        f"Realistic R (after slippage+fees): {r_multiple_realistic:+.3f}. PnL: NGN {pnl_ngn:,.0f}."
    )


def _check_for_entry(symbol: str, asset_id: int, strategy, df, latest_candle_time,
                      backtest_summary: dict, regime_breakdown: dict) -> None:
    with get_session() as session:
        asset = session.get(Asset, asset_id)
        if has_signal_for_candle(session, asset, latest_candle_time):
            print(f"[{symbol}] Already decided for this candle ({latest_candle_time}); waiting for the next one.")
            return
        portfolio = build_portfolio_state(session, account_baseline=RISK.account_size_ngn)

    proposal = build_proposal(
        df, symbol, strategy=strategy, risk_config=RISK, portfolio=portfolio,
        backtest_summary=backtest_summary,
    )

    if proposal is None:
        print(f"[{symbol}] No setup on latest closed candle ({latest_candle_time}).")
        return

    verdict = evaluate_trade(proposal, portfolio, RISK)

    with get_session() as session:
        asset = get_or_create_asset(session, symbol, exchange=MARKET.exchange, category=MARKET.category)
        signal = save_signal(session, asset, proposal, verdict, triggering_candle_time=latest_candle_time)
        signal_id = signal.id

    if not verdict.approved:
        print(f"[{symbol}] Risk engine REJECTED (signal #{signal_id}): {verdict.reason}")
        return

    summary = explain_full_trade_review(
        proposal, verdict, RISK, strategy, DATA_SOURCE, regime_breakdown=regime_breakdown, is_paper=True,
    )
    print("\n" + summary + "\n")

    decision_input = input(f"[{symbol}] Approve this trade? (y/n): ").strip().lower()

    if decision_input == "y":
        side = _entry_side(proposal.direction)
        entry_fill_price = _apply_slippage(proposal.entry_price, side, BACKTEST.slippage_pct)
        entry_fee = _fee(proposal.position_size * entry_fill_price, BACKTEST.fee_pct)

        with get_session() as session:
            signal = session.get(Signal, signal_id)
            record_human_decision(session, signal, HumanDecision.APPROVED, None)
            trade = create_paper_trade(
                session, signal, proposal, entry_fill_price, entry_fee,
                latest_candle_time, summary, DATA_SOURCE,
            )
            trade_id = trade.id
        print(f"[{symbol}] Paper trade #{trade_id} OPENED at {entry_fill_price:.2f} "
              f"(proposed {proposal.entry_price}).")
    else:
        reason_input = input("Reason for declining (optional, press Enter to skip): ").strip() or None
        with get_session() as session:
            signal = session.get(Signal, signal_id)
            record_human_decision(session, signal, HumanDecision.DECLINED, reason_input)
        print(f"[{symbol}] Declined (signal #{signal_id}). Logged.")


def main():
    print(f"Paper trading engine starting -- polling every {POLL_INTERVAL_SECONDS}s. Ctrl+C to stop.")
    while True:
        for symbol in MARKET.pairs:
            try:
                strategy = STRATEGY_FOR_SYMBOL[symbol]
                run_once(symbol, strategy)
            except Exception as e:
                print(f"[{symbol}] Error during poll cycle: {e!r}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
