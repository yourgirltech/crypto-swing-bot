"""
Regime classifier.

Every label is traceable to the numbers behind it — no black box.
Uses: trend slope (EMA direction + magnitude), ATR relative to its own
history (volatility expansion/contraction), and recent drawdown/rally
magnitude for the "panic recovery" case.
"""

from enum import Enum
import pandas as pd
import numpy as np


class Regime(Enum):
    STRONG_BULL = "strong_bull_trend"
    WEAK_BULL = "weak_bull_trend"
    SIDEWAYS = "sideways"
    HYPERBOLIC = "hyperbolic"
    STRONG_BEAR = "strong_bear_trend"
    PANIC_RECOVERY = "panic_recovery"


def classify_regime(df: pd.DataFrame, ema_fast_col: str, ema_slow_col: str,
                     atr_col: str = "atr", lookback: int = 20) -> dict:
    """
    df must already have EMA and ATR columns (see indicators.add_all_indicators).
    Returns the regime for the LATEST bar plus the underlying numbers used,
    so the reasoning is always inspectable.
    """
    recent = df.tail(lookback).copy()
    close = recent["close"]

    # trend slope: % change of the slow EMA over the lookback window
    slow_ema_start = recent[ema_slow_col].iloc[0]
    slow_ema_end = recent[ema_slow_col].iloc[-1]
    slope_pct = (slow_ema_end - slow_ema_start) / slow_ema_start * 100

    # volatility: current ATR vs its own trailing average (expansion/contraction)
    atr_now = df[atr_col].iloc[-1]
    atr_avg = df[atr_col].tail(lookback * 3).mean()
    atr_ratio = atr_now / atr_avg if atr_avg else 1.0

    # drawdown / rally magnitude over the lookback window, for panic/recovery detection
    period_high = close.max()
    period_low = close.min()
    last_close = close.iloc[-1]
    drawdown_from_high_pct = (last_close - period_high) / period_high * 100
    rally_from_low_pct = (last_close - period_low) / period_low * 100

    fast_above_slow = recent[ema_fast_col].iloc[-1] > recent[ema_slow_col].iloc[-1]

    # --- classification rules, in priority order ---
    if atr_ratio > 2.0 and slope_pct > 15:
        regime = Regime.HYPERBOLIC
    elif drawdown_from_high_pct < -15 and rally_from_low_pct > 8:
        regime = Regime.PANIC_RECOVERY
    elif slope_pct > 5 and fast_above_slow:
        regime = Regime.STRONG_BULL
    elif slope_pct > 0 and fast_above_slow:
        regime = Regime.WEAK_BULL
    elif slope_pct < -5 and not fast_above_slow:
        regime = Regime.STRONG_BEAR
    else:
        regime = Regime.SIDEWAYS

    return {
        "regime": regime.value,
        "slope_pct": round(slope_pct, 2),
        "atr_ratio": round(atr_ratio, 2),
        "drawdown_from_high_pct": round(drawdown_from_high_pct, 2),
        "rally_from_low_pct": round(rally_from_low_pct, 2),
        "fast_above_slow": bool(fast_above_slow),
    }
