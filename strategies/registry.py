"""
Strategy registry -- Milestone 6, extended for Milestone 10.

STRATEGY_FOR_SYMBOL is the single source of truth for "which strategy
runs on which symbol" -- paper_trading/engine.py and main.py both import
it from here rather than each keeping their own copy, so the live engine,
the one-shot demo script, and this registry (which drives the frontend
Strategies page via api/routes/strategies.py) can never drift apart on
which strategy is actually assigned to which symbol.

No `strategies` DB table exists yet (deferred, see db/models.py's
Milestone 1 docstring) -- real backtested performance comes from
persisted backtest_runs (linked by symbol via the API layer /
frontend/src/app/strategies/page.tsx), not duplicated here. This module
describes each strategy from its ACTUAL instantiated parameters, not
fabricated metadata.

list_strategies(symbols) returns ONE StrategyInfo per DISTINCT strategy
actually assigned to any of the given symbols -- grouped by strategy, not
"the first/only strategy applied to every symbol given" (that was the
Milestone 6-era assumption, valid when there was exactly one strategy in
the whole codebase; it stopped being valid the moment a second
symbol/strategy pairing existed -- see docs/ARCHITECTURE.md's Milestone
10 section).
"""

from dataclasses import dataclass
from typing import Dict, List

from strategies.base import Strategy
from strategies.trend_continuation_bos import TrendContinuationBOS
from strategies.breakout import Breakout

# Real source of truth -- see module docstring. Strategy instances are
# stateless (strategies/base.py's own docstring), so sharing one instance
# per symbol across the live engine, main.py, and this registry is safe.
STRATEGY_FOR_SYMBOL: Dict[str, Strategy] = {
    "BTCUSDT": TrendContinuationBOS(),
    "ETHUSDT": Breakout(),
}

_DESCRIPTIONS = {
    "trend_continuation_bos": (
        "Trend-continuation Break of Structure: enters when price breaks a swing "
        "point in the direction of the prevailing trend, confirmed by an EMA21/EMA50 "
        "cross and RSI not in an extreme. The weak_bull_trend regime additionally "
        "requires price trading above EMA21, not just the cross."
    ),
    "breakout": (
        "Donchian-channel breakout: enters when price closes beyond the highest "
        "high (long) or lowest low (short) of the prior N-bar range, confirmed by "
        "an ATR-expansion filter (rejects breaks on contracting volatility) and a "
        "rejection of RSI-extreme entries. Fires on the range-to-trend transition "
        "itself, independent of the swing/BOS structure TrendContinuationBOS uses."
    ),
}


@dataclass
class StrategyInfo:
    name: str
    description: str
    symbols: List[str]
    parameters: dict


def strategy_parameters(strategy: Strategy) -> dict:
    if strategy.name == "trend_continuation_bos":
        return {
            "atr_stop_mult": strategy.atr_stop_mult,
            "reward_risk": strategy.reward_risk,
            "swing_lookback": strategy.swing_lookback,
            "rsi_extreme": list(strategy.rsi_extreme),
        }
    if strategy.name == "breakout":
        return {
            "channel_lookback": strategy.channel_lookback,
            "atr_stop_mult": strategy.atr_stop_mult,
            "reward_risk": strategy.reward_risk,
            "min_atr_expansion": strategy.min_atr_expansion,
            "rsi_extreme": list(strategy.rsi_extreme),
        }
    return {}


def list_strategies(symbols: List[str]) -> List[StrategyInfo]:
    by_strategy: Dict[str, tuple] = {}
    for symbol in symbols:
        strategy = STRATEGY_FOR_SYMBOL.get(symbol)
        if strategy is None:
            continue  # no strategy assigned to this symbol -- nothing to describe
        strategy_obj, assigned_symbols = by_strategy.setdefault(strategy.name, (strategy, []))
        assigned_symbols.append(symbol)

    return [
        StrategyInfo(
            name=name,
            description=_DESCRIPTIONS.get(name, ""),
            symbols=assigned_symbols,
            parameters=strategy_parameters(strategy_obj),
        )
        for name, (strategy_obj, assigned_symbols) in by_strategy.items()
    ]
