"""
Market structure engine.

Everything here is deterministic — pure price-data math, no LLM, no
subjectivity. This is the backbone the rest of the system (regime,
strategies, proposals) builds on top of.

Core concepts implemented:
- Swing high / swing low detection
- HH/HL/LH/LL sequencing -> trend state (up / down / range)
- Support & resistance zones, including S->R flip detection
- Liquidity concepts: equal highs/lows, previous-day/session high/low
- Break of Structure (BOS) and Change of Character (CHoCH)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import pandas as pd
import numpy as np


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


class TrendState(Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"


@dataclass
class Swing:
    index: int
    time: pd.Timestamp
    price: float
    kind: SwingType
    label: Optional[str] = None  # "HH", "HL", "LH", "LL" once classified


@dataclass
class Zone:
    price_low: float
    price_high: float
    kind: str          # "support" | "resistance"
    origin_index: int
    flipped: bool = False   # True if this zone has flipped role (S->R or R->S)


def find_swings(df: pd.DataFrame, lookback: int = 5) -> List[Swing]:
    """
    A swing high is a bar whose high is the max within `lookback` bars on
    each side. A swing low is the symmetric case for lows. This avoids
    curve-fitting to single-bar noise.
    """
    swings: List[Swing] = []
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    for i in range(lookback, n - lookback):
        window_high = highs[i - lookback:i + lookback + 1]
        if highs[i] == window_high.max() and np.argmax(window_high) == lookback:
            swings.append(Swing(index=i, time=df["open_time"].iloc[i], price=highs[i], kind=SwingType.HIGH))

        window_low = lows[i - lookback:i + lookback + 1]
        if lows[i] == window_low.min() and np.argmin(window_low) == lookback:
            swings.append(Swing(index=i, time=df["open_time"].iloc[i], price=lows[i], kind=SwingType.LOW))

    swings.sort(key=lambda s: s.index)
    return swings


class SwingTracker:
    """
    Incremental swing detector for walk-forward use (e.g. the backtest
    engine, which re-checks a growing window at every bar).

    A bar's swing-high/swing-low classification depends only on the fixed
    `lookback` bars on each side of it (see find_swings) — so once a bar
    has `lookback` bars of history after it, its classification is final
    and will never change as more bars are appended later. This lets us
    classify each bar exactly once (amortized O(1) per new bar) instead
    of re-scanning the whole window from scratch on every call, while
    producing byte-identical Swing objects to
    find_swings(df, lookback) called on the same full df.
    """

    def __init__(self, lookback: int = 5):
        self.lookback = lookback
        self.swings: List[Swing] = []
        self._checked_through = lookback - 1  # last bar index already classified

    def update(self, df: pd.DataFrame) -> List[Swing]:
        """
        df: the current window (grows over time, same bars 0..k unchanged
        across calls — only append-only growth is supported). Returns the
        running list of confirmed swings, same object each call.
        """
        n = len(df)
        confirmable_through = n - 1 - self.lookback
        if confirmable_through <= self._checked_through:
            return self.swings

        highs = df["high"].values
        lows = df["low"].values

        for i in range(self._checked_through + 1, confirmable_through + 1):
            window_high = highs[i - self.lookback:i + self.lookback + 1]
            if highs[i] == window_high.max() and np.argmax(window_high) == self.lookback:
                self.swings.append(Swing(index=i, time=df["open_time"].iloc[i], price=highs[i], kind=SwingType.HIGH))

            window_low = lows[i - self.lookback:i + self.lookback + 1]
            if lows[i] == window_low.min() and np.argmin(window_low) == self.lookback:
                self.swings.append(Swing(index=i, time=df["open_time"].iloc[i], price=lows[i], kind=SwingType.LOW))

        self._checked_through = confirmable_through
        return self.swings


def label_swing_sequence(swings: List[Swing]) -> List[Swing]:
    """
    Walk the swing list and label each high as HH/LH relative to the prior
    swing high, and each low as HL/LL relative to the prior swing low.
    """
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None

    for s in swings:
        if s.kind == SwingType.HIGH:
            if last_high is not None:
                s.label = "HH" if s.price > last_high.price else "LH"
            last_high = s
        else:
            if last_low is not None:
                s.label = "HL" if s.price > last_low.price else "LL"
            last_low = s

    return swings


def classify_trend(swings: List[Swing], recent_n: int = 4) -> TrendState:
    """
    Look at the most recent labeled swings. Consistent HH+HL -> uptrend.
    Consistent LH+LL -> downtrend. Mixed -> range.
    """
    labeled = [s for s in swings if s.label is not None][-recent_n:]
    if len(labeled) < 2:
        return TrendState.RANGE

    labels = [s.label for s in labeled]
    bullish = all(l in ("HH", "HL") for l in labels)
    bearish = all(l in ("LH", "LL") for l in labels)

    if bullish:
        return TrendState.UPTREND
    if bearish:
        return TrendState.DOWNTREND
    return TrendState.RANGE


def detect_bos_choch(swings: List[Swing], current_trend: TrendState) -> Optional[str]:
    """
    BOS (Break of Structure): price breaks a swing point in the direction
    of the current trend -> trend continuation confirmation.
    CHoCH (Change of Character): price breaks a swing point AGAINST the
    current trend -> first warning the trend may be reversing.
    Returns "BOS", "CHoCH", or None.
    """
    labeled = [s for s in swings if s.label is not None]
    if len(labeled) < 3:
        return None

    last = labeled[-1]

    if current_trend == TrendState.UPTREND:
        if last.kind == SwingType.HIGH and last.label == "HH":
            return "BOS"
        if last.kind == SwingType.LOW and last.label == "LL":
            return "CHoCH"
    elif current_trend == TrendState.DOWNTREND:
        if last.kind == SwingType.LOW and last.label == "LL":
            return "BOS"
        if last.kind == SwingType.HIGH and last.label == "HH":
            return "CHoCH"

    return None


def find_equal_levels(swings: List[Swing], tolerance_pct: float = 0.15) -> List[List[Swing]]:
    """
    Groups swing highs (or lows) that sit within tolerance_pct of each
    other into "equal high / equal low" liquidity clusters — classic
    stop-hunt / liquidity-pool zones.
    """
    groups: List[List[Swing]] = []
    for kind in (SwingType.HIGH, SwingType.LOW):
        pts = sorted([s for s in swings if s.kind == kind], key=lambda s: s.price)
        used = set()
        for i, s in enumerate(pts):
            if i in used:
                continue
            cluster = [s]
            for j in range(i + 1, len(pts)):
                if j in used:
                    continue
                if abs(pts[j].price - s.price) / s.price * 100 <= tolerance_pct:
                    cluster.append(pts[j])
                    used.add(j)
            if len(cluster) > 1:
                groups.append(cluster)
    return groups


def build_sr_zones(swings: List[Swing], width_pct: float = 0.25) -> List[Zone]:
    """
    Builds support/resistance zones around swing points. A zone is
    "resistance" if built from a swing high, "support" if from a swing low.
    Flip detection (S->R or R->S) is left to be checked against later price
    action by the caller (compare current price interaction to zone.kind).
    """
    zones: List[Zone] = []
    for s in swings:
        half_width = s.price * (width_pct / 100)
        kind = "resistance" if s.kind == SwingType.HIGH else "support"
        zones.append(Zone(
            price_low=s.price - half_width,
            price_high=s.price + half_width,
            kind=kind,
            origin_index=s.index,
        ))
    return zones


def session_and_prior_day_levels(df: pd.DataFrame) -> dict:
    """
    Returns previous day's high/low and current session's high/low so far.
    Assumes df has a datetime 'open_time' column and is sorted ascending.
    """
    df = df.copy()
    df["date"] = df["open_time"].dt.date
    dates = sorted(df["date"].unique())

    result = {"prev_day_high": None, "prev_day_low": None,
              "session_high": None, "session_low": None}

    if len(dates) >= 2:
        prev_day = df[df["date"] == dates[-2]]
        result["prev_day_high"] = prev_day["high"].max()
        result["prev_day_low"] = prev_day["low"].min()

    current_day = df[df["date"] == dates[-1]]
    if not current_day.empty:
        result["session_high"] = current_day["high"].max()
        result["session_low"] = current_day["low"].min()

    return result


def analyze_structure(df: pd.DataFrame, lookback: int = 5, equal_tolerance_pct: float = 0.15) -> dict:
    """
    Convenience wrapper: runs the full structure analysis pipeline on a
    DataFrame and returns a summary dict, the shape a proposal/synthesis
    layer would consume.
    """
    swings = find_swings(df, lookback=lookback)
    swings = label_swing_sequence(swings)
    trend = classify_trend(swings)
    bos_choch = detect_bos_choch(swings, trend)
    equal_levels = find_equal_levels(swings, tolerance_pct=equal_tolerance_pct)
    zones = build_sr_zones(swings)
    day_levels = session_and_prior_day_levels(df)

    return {
        "trend": trend.value,
        "last_signal": bos_choch,
        "swings": swings,
        "equal_level_clusters": equal_levels,
        "sr_zones": zones,
        "day_levels": day_levels,
    }
