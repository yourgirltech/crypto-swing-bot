"""
A deliberately lean indicator set — a confluence stack, not a collection.

Trend filter: EMA fast/slow
Momentum: RSI
Volatility (for stop-loss distance + regime input): ATR
Optional confirmation: Bollinger Bands
"""

import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50)  # neutral fill for the warmup period


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return pd.DataFrame({
        "bb_mid": mid,
        "bb_upper": mid + num_std * std,
        "bb_lower": mid - num_std * std,
    })


def add_all_indicators(df: pd.DataFrame, ema_fast: int = 21, ema_slow: int = 50,
                        rsi_period: int = 14, atr_period: int = 14,
                        bb_period: int = 20, bb_std: float = 2.0) -> pd.DataFrame:
    """
    Returns a copy of df with indicator columns appended.
    """
    out = df.copy()
    out[f"ema_{ema_fast}"] = ema(out["close"], ema_fast)
    out[f"ema_{ema_slow}"] = ema(out["close"], ema_slow)
    out["rsi"] = rsi(out["close"], rsi_period)
    out["atr"] = atr(out, atr_period)

    bb = bollinger_bands(out["close"], bb_period, bb_std)
    out = pd.concat([out, bb], axis=1)

    out["trend_filter"] = np.where(
        out[f"ema_{ema_fast}"] > out[f"ema_{ema_slow}"], "bullish", "bearish"
    )

    return out
