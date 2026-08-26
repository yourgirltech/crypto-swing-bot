"""
Plain-language reporting layer.

Takes a backtest summary dict (backtest.backtest_engine.BacktestResult.summary()),
optionally a regime breakdown (BacktestResult.by_regime()), and/or a live
TradeProposal (proposals.trade_proposal.TradeProposal), and produces a
deterministic, template-based plain-English explanation.

This is NOT an LLM call. Every sentence is filled in directly from the
numbers passed in — nothing here invents a probability, a confidence
level, or a causal claim that isn't supported by the input data. When a
number rests on a small sample, that is stated explicitly rather than
smoothed over. This exists so the human reviewing a proposal understands
what the backtested stats actually mean in practice, in the same way the
deterministic core already refuses to guess at "chance of profit" without
a backtested number behind it.
"""

from typing import Optional, Dict

# Sample-size thresholds for how much weight to put on a stat. These are
# judgment calls, not derived from the data itself — worth revisiting once
# real trade volume exists.
MIN_SAMPLE_USABLE = 10       # below this, treat the number as a hint only
MIN_SAMPLE_FOR_CONFIDENCE = 30  # below this, still call out the small sample


def _confidence_note(sample_size: Optional[int]) -> str:
    if not sample_size:
        return "no backtested trades exist for this yet, so there is no confidence-backed number at all."
    if sample_size < MIN_SAMPLE_USABLE:
        return (
            f"only {sample_size} historical trades back this number — too few to treat as "
            f"reliable. Read it as an early hint, not a fact."
        )
    if sample_size < MIN_SAMPLE_FOR_CONFIDENCE:
        return (
            f"this is based on {sample_size} historical trades, which is a small sample. "
            f"The true win rate/expectancy could differ meaningfully from what's shown here."
        )
    return f"this is based on {sample_size} historical trades — a reasonably sized sample for this system's history so far."


def explain_backtest_summary(summary: dict) -> str:
    """
    Plain-English translation of a BacktestResult.summary() dict:
    {total_trades, win_rate_pct, avg_win_r, avg_loss_r, expectancy_r, max_drawdown_pct}
    """
    trades = summary.get("total_trades", 0)
    if not trades:
        return "No closed trades in this backtest — there's nothing yet to draw a conclusion from."

    win_rate = summary.get("win_rate_pct", 0.0)
    avg_win = summary.get("avg_win_r", 0.0)
    avg_loss = summary.get("avg_loss_r", 0.0)
    expectancy = summary.get("expectancy_r", 0.0)
    max_dd = summary.get("max_drawdown_pct", 0.0)

    lines = []

    lines.append(
        f"Out of {trades} historical trades matching this setup, {win_rate}% were winners "
        f"and {round(100 - win_rate, 1)}% were losers."
    )

    if expectancy > 0:
        verdict = "profitable on average"
    elif expectancy < 0:
        verdict = "unprofitable on average"
    else:
        verdict = "break-even on average"

    lines.append(
        f"On average this setup has been {verdict}: for every 1 unit of capital risked, it has "
        f"historically returned about {expectancy:+.3f} units per trade over time. As an example, "
        f"if you risked ₦10,000 on every trade like this, the historical average outcome per trade "
        f"has been about ₦{expectancy * 10000:,.0f} (this is illustrative, not a promise)."
    )

    lines.append(
        f"When it wins, it wins about {avg_win:.1f}x the amount risked; when it loses, it loses "
        f"about {abs(avg_loss):.1f}x the amount risked."
        + (
            " That's why a win rate under 50% can still be profitable overall — the winners are "
            "structured to be bigger than the losers."
            if avg_win > abs(avg_loss) and win_rate < 50 and expectancy > 0
            else " In this case the payoff shape wasn't enough to offset the low win rate — the "
                 "setup lost money overall despite bigger winners than losers."
            if avg_win > abs(avg_loss) and win_rate < 50 and expectancy <= 0
            else ""
        )
    )

    lines.append(
        f"The worst peak-to-trough equity decline seen in this backtest was {abs(max_dd):.1f}%. "
        f"That's the roughest historical stretch, not a ceiling — a future drawdown is not "
        f"guaranteed to stay within this range."
    )

    lines.append(f"Confidence: {_confidence_note(trades)}")

    return "\n".join(lines)


def explain_regime_breakdown(regime_breakdown: Dict[str, dict], symbol: str = "") -> str:
    """
    regime_breakdown: {regime_name: {"trades": int, "win_rate_pct": float, "expectancy_r": float}}
    (see BacktestResult.by_regime())
    """
    if not regime_breakdown:
        return "No regime breakdown available."

    header = f"Regime breakdown{f' for {symbol}' if symbol else ''}:"
    lines = [header]

    ranked = sorted(regime_breakdown.items(), key=lambda kv: kv[1].get("expectancy_r", 0), reverse=True)

    for regime, stats in ranked:
        trades = stats.get("trades", 0)
        win_rate = stats.get("win_rate_pct", 0.0)
        expectancy = stats.get("expectancy_r", 0.0)
        readable = regime.replace("_", " ")

        if trades == 0:
            lines.append(f"- {readable}: no trades were taken in this regime.")
            continue

        if expectancy > 0.1:
            verdict = "worked well"
        elif expectancy >= -0.05:
            verdict = "was roughly break-even"
        else:
            verdict = "performed poorly"

        lines.append(
            f"- {readable}: {trades} trades, {win_rate}% win rate, {expectancy:+.3f}R average — "
            f"this setup {verdict} in this regime ({_confidence_note(trades)})"
        )

    sideways = regime_breakdown.get("sideways")
    trending = [v for k, v in regime_breakdown.items() if k != "sideways" and v.get("trades", 0) > 0]
    if sideways and sideways.get("trades", 0) > 0 and trending:
        avg_trending_expectancy = sum(v["expectancy_r"] for v in trending) / len(trending)
        if sideways["expectancy_r"] < avg_trending_expectancy:
            lines.append(
                "This matches the structural expectation: a trend-continuation setup should "
                "underperform in a sideways/range regime, since there's no sustained trend for a "
                "breakout to continue into — and that's what these numbers show."
            )
        else:
            lines.append(
                "Note: in this sample, the setup did NOT clearly underperform in the sideways "
                "regime relative to trending regimes — worth re-checking that assumption rather "
                "than taking 'trend-continuation fails in chop' for granted here."
            )

    return "\n".join(lines)


def explain_trade_proposal(proposal) -> str:
    """
    Plain-English read of a live TradeProposal (proposals.trade_proposal.TradeProposal):
    the setup, what history suggests about trades like it, and the risk being taken.
    Adds no confidence beyond what backtested_win_rate_pct / backtested_sample_size /
    backtested_expectancy_r on the proposal actually support.
    """
    if proposal is None:
        return "There is no active trade setup right now. The system does not force a trade to exist."

    lines = []

    lines.append(
        f"{proposal.symbol}: a {proposal.direction} setup ({proposal.setup_type.replace('_', ' ')}) "
        f"in a {proposal.trend.replace('_', ' ')}, current market regime is "
        f"{proposal.regime.replace('_', ' ')}."
    )

    lines.append(
        f"Proposed entry at {proposal.entry_price}, stop at {proposal.stop_price}, target at "
        f"{proposal.target_price} — a {proposal.reward_risk_ratio:.1f}:1 reward-to-risk setup. "
        f"Taking this trade risks ₦{proposal.risk_amount:,.0f} (position size "
        f"{proposal.position_size})."
    )

    if proposal.backtested_sample_size and proposal.backtested_win_rate_pct is not None:
        lines.append(
            f"History for this exact setup type: {proposal.backtested_win_rate_pct}% win rate "
            f"over {proposal.backtested_sample_size} trades, average expectancy "
            f"{proposal.backtested_expectancy_r:+.3f}R per trade. "
            f"{_confidence_note(proposal.backtested_sample_size)}"
        )
    else:
        lines.append(
            "No backtested track record exists yet for this exact setup type — the win rate and "
            "expectancy are unknown here, not assumed to be good."
        )

    lines.append(
        "This is a description of what happened historically when a similar setup appeared, not "
        "a guarantee — any single trade can land outside these averages."
    )

    return "\n".join(lines)


def full_report(backtest_summary: dict, regime_breakdown: Optional[dict] = None,
                 proposal=None, symbol: str = "") -> str:
    """Combines all three sections into one report string."""
    sections = [explain_backtest_summary(backtest_summary)]
    if regime_breakdown:
        sections.append(explain_regime_breakdown(regime_breakdown, symbol=symbol))
    if proposal is not None:
        sections.append(explain_trade_proposal(proposal))
    elif regime_breakdown is not None or backtest_summary:
        sections.append(explain_trade_proposal(None))
    return "\n\n".join(sections)


def explain_full_trade_review(proposal, verdict, risk_config, strategy, data_source: str,
                               regime_breakdown: Optional[dict] = None, is_paper: bool = True) -> str:
    """
    Milestone 4: the FULL review shown to a human before they approve or
    decline a risk-engine-APPROVED proposal (paper_trading/engine.py). Only
    ever called on an APPROVED verdict — a REJECTED one is logged with its
    reason and never reaches a human (see that module).

    Every number here comes from `proposal` (the setup itself) or
    `verdict.metrics` (populated by risk.risk_engine.evaluate_trade() as it
    checks each rule) — nothing is recomputed or re-invented here, so this
    can never drift from what the risk engine actually evaluated.
    """
    if not verdict.approved:
        raise ValueError(
            "explain_full_trade_review() is for risk-engine-APPROVED proposals only — "
            "a REJECTED verdict should be logged directly with verdict.reason, not shown to a human."
        )

    lines = []
    m = verdict.metrics

    # 1. What the setup is and why it triggered.
    lines.append(
        f"=== {proposal.symbol}: {proposal.direction.upper()} setup ({proposal.setup_type.replace('_', ' ')}) ===\n"
        f"Trend: {proposal.trend.replace('_', ' ')}. Market regime: {proposal.regime.replace('_', ' ')}. "
        f"RSI at entry: {proposal.rsi}."
    )
    # weak_bull_trend's extra EMA21 confirmation is the one regime-specific
    # rule this strategy has today (see strategies/trend_continuation_bos.py)
    # — named explicitly here since the user asked which confirmation fired.
    # NOTE: this couples the reporting layer to TrendContinuationBOS's one
    # known regime-specific rule; if/when a second strategy adds its own
    # confirmation rules, this should become a Strategy.describe_confirmation()
    # hook instead of more regime-name checks piling up here.
    if proposal.regime == "weak_bull_trend":
        lines.append(
            "Confirmation: weak_bull_trend requires price to be trading above EMA21 (not just the "
            "EMA21>EMA50 cross) — that extra condition fired and passed for this setup."
        )

    # 2. Backtested track record for this exact setup type.
    if proposal.backtested_sample_size and proposal.backtested_win_rate_pct is not None:
        lines.append(
            f"\nBacktested track record for this setup type: {proposal.backtested_win_rate_pct}% win rate, "
            f"{proposal.backtested_expectancy_r:+.3f}R average expectancy. "
            f"({_confidence_note(proposal.backtested_sample_size)})"
        )
    else:
        lines.append(
            "\nNo backtested track record exists yet for this exact setup type — win rate and "
            "expectancy are unknown, not assumed to be good."
        )

    if regime_breakdown and proposal.regime in regime_breakdown:
        regime_stats = regime_breakdown[proposal.regime]
        lines.append(
            f"Regime-specific ({proposal.regime.replace('_', ' ')}) stats: "
            f"{regime_stats.get('win_rate_pct', 0.0)}% win rate, "
            f"{regime_stats.get('expectancy_r', 0.0):+.3f}R average, over {regime_stats.get('trades', 0)} trades — "
            + ("consistent with" if abs(regime_stats.get('expectancy_r', 0.0) - (proposal.backtested_expectancy_r or 0.0)) < 0.05
               else "notably DIFFERENT from")
            + " the overall backtested figure above."
        )

    # 3. Plain-language profit vs. loss estimate, grounded ONLY in the
    # backtested win rate/expectancy above -- never invented or rounded up.
    loss_ngn = proposal.risk_amount
    win_ngn = proposal.risk_amount * proposal.reward_risk_ratio
    if proposal.backtested_sample_size and proposal.backtested_win_rate_pct is not None:
        lose_rate = round(100 - proposal.backtested_win_rate_pct, 1)
        lines.append(
            f"\nLikely outcome, grounded in that backtested history (not a promise): historically "
            f"about {proposal.backtested_win_rate_pct}% of trades like this won (gaining roughly "
            f"₦{win_ngn:,.0f}) and about {lose_rate}% lost (losing roughly ₦{loss_ngn:,.0f})."
        )
    else:
        lines.append(
            f"\nNo historical win rate exists for this setup type, so there is no basis to estimate "
            f"how LIKELY a win vs. loss is here — only the raw payoff shape is known: a win is worth "
            f"roughly ₦{win_ngn:,.0f}, a loss roughly ₦{loss_ngn:,.0f}."
        )

    # 4. Entry / stop / target / reward:risk, with the stop's reasoning.
    stop_dist = abs(proposal.entry_price - proposal.stop_price)
    atr_mult = getattr(strategy, "atr_stop_mult", None)
    stop_reasoning = (
        f"an ATR-based stop ({atr_mult}x the 14-period ATR at entry), not a fixed percentage — "
        f"it adapts to how volatile price actually is right now"
        if atr_mult is not None else
        "an ATR-based stop (adapts to current volatility rather than a fixed percentage)"
    )
    lines.append(
        f"\nEntry: {proposal.entry_price}. Stop-loss: {proposal.stop_price} "
        f"(₦{stop_dist:,.2f} / {stop_dist / proposal.entry_price * 100:.2f}% away — {stop_reasoning}). "
        f"Take-profit: {proposal.target_price} ({proposal.reward_risk_ratio:.1f}:1 reward-to-risk)."
    )

    # 5. Position size and actual NGN amount risked.
    lines.append(
        f"Position size: {proposal.position_size} units. Amount actually risked on this trade: "
        f"₦{proposal.risk_amount:,.0f}."
    )

    # 6. Risk engine budget status -- how much of each limit this trade uses.
    lines.append(
        f"\nRisk engine status (after this trade, if approved):\n"
        f"  Daily loss budget: {m.get('daily_pnl_pct', 0.0):.2f}% used of the "
        f"{risk_config.max_daily_loss_pct:.2f}% circuit-breaker limit.\n"
        f"  Weekly loss budget: {m.get('weekly_pnl_pct', 0.0):.2f}% used of the "
        f"{risk_config.max_weekly_loss_pct:.2f}% circuit-breaker limit.\n"
        f"  Open positions: {m.get('open_positions_count', 0) + 1}/{risk_config.max_open_positions} "
        f"(after this trade).\n"
        f"  Portfolio exposure: {m.get('portfolio_exposure_pct', 0.0):.2f}% of equity, of a "
        f"{risk_config.max_portfolio_exposure_pct:.2f}% limit.\n"
        f"  Correlated exposure ({'+'.join(m.get('correlated_group', [proposal.symbol]))}): "
        f"{m.get('correlated_exposure_pct', 0.0):.2f}% of a {risk_config.max_correlated_exposure_pct:.2f}% limit.\n"
        f"  Current drawdown: {m.get('drawdown_pct', 0.0):.2f}% of a {risk_config.max_drawdown_pct:.2f}% "
        f"kill-switch limit."
    )

    # 7. Caveats.
    caveats = []
    if data_source != "bybit":
        caveats.append(
            f"Data source for this signal is {data_source.upper()}, not Bybit (the documented execution "
            f"exchange) — prices/candles differ slightly between exchanges."
        )
    caveats.append(
        "This is PAPER trading" + (" — no real capital is at risk" if is_paper else "") + "."
    )
    lines.append("\nCaveats:\n" + "\n".join(f"  - {c}" for c in caveats))

    return "\n".join(lines)
