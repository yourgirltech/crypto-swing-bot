"""
Strategy registry -- Milestone 6.

No `strategies` DB table exists yet (deferred, see db/models.py's
Milestone 1 docstring) -- there is exactly one strategy in this codebase
today (strategies.trend_continuation_bos.TrendContinuationBOS). This
module describes it from its ACTUAL instantiated parameters, not
fabricated metadata. Real backtested performance for it comes from
backtest/history.py's persisted backtest_runs (linked by symbol via the
API layer), not duplicated here.
"""

from dataclasses import dataclass
from typing import List

from strategies.trend_continuation_bos import TrendContinuationBOS


@dataclass
class StrategyInfo:
    name: str
    description: str
    symbols: List[str]
    parameters: dict


def list_strategies(symbols: List[str]) -> List[StrategyInfo]:
    strategy = TrendContinuationBOS()
    return [
        StrategyInfo(
            name=strategy.name,
            description=(
                "Trend-continuation Break of Structure: enters when price breaks a swing "
                "point in the direction of the prevailing trend, confirmed by an EMA21/EMA50 "
                "cross and RSI not in an extreme. The weak_bull_trend regime additionally "
                "requires price trading above EMA21, not just the cross."
            ),
            symbols=symbols,
            parameters={
                "atr_stop_mult": strategy.atr_stop_mult,
                "reward_risk": strategy.reward_risk,
                "swing_lookback": strategy.swing_lookback,
                "rsi_extreme": list(strategy.rsi_extreme),
            },
        )
    ]
