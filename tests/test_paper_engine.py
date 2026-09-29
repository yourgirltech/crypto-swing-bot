"""
Regression tests for the two paper-engine bugs fixed 2026-09-29:
1. OKX's history-candles returns the still-forming candle; only closed
   candles may reach the engine / save_candles().
2. Exits were checked on the latest candle only, so a stop/target hit
   during downtime was never seen.
Neither test touches the network or the database.
"""

from datetime import datetime
from unittest.mock import patch

import pandas as pd

from data.okx_client import OKXClient
from paper_trading.engine import _find_exit
from strategies.trend_continuation_bos import TrendContinuationBOS


# --- 1. Closed candles only ----------------------------------------------------

class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return {"code": "0", "data": self._rows}


def _okx_row(ts_ms, close, confirm):
    return [str(ts_ms), "1", "2", "0.5", str(close), "10", "0", "0", confirm]


def test_historical_klines_drops_the_forming_candle():
    step = 4 * 3600 * 1000
    newest = 1_790_668_800_000
    # Newest-first, like OKX: forming candle, then 99 closed ones = a FULL batch of 100.
    rows = [_okx_row(newest, 999, "0")] + [_okx_row(newest - i * step, 100 + i, "1") for i in range(1, 100)]
    pages = [rows, []]
    with patch("data.okx_client.requests.get", side_effect=lambda *a, **k: _Resp(pages.pop(0))), \
         patch("data.okx_client.time.sleep"):
        df = OKXClient(testnet=False).get_historical_klines("BTCUSDT", "240", days=40)

    assert len(df) == 99
    assert 999.0 not in df["close"].values
    assert "confirmed" not in df.columns
    # Pagination still continued past the first batch (the full-batch check
    # uses the raw count, so dropping the forming row didn't stop it early).
    assert pages == []


# --- 2. Exit catch-up ------------------------------------------------------------

def _candles(bars):
    """bars: list of (high, low), one 4H candle each starting 2026-08-26 16:00."""
    times = pd.date_range("2026-08-26 16:00", periods=len(bars), freq="4h")
    return pd.DataFrame({"open_time": times, "high": [b[0] for b in bars], "low": [b[1] for b in bars]})


ENTRY = datetime(2026, 8, 26, 16)


def test_finds_a_target_hit_several_candles_back():
    # entry candle (ignored even though it spikes), 2 quiet candles, target hit, then more quiet ones
    df = _candles([(200, 50), (101, 99), (101, 99), (107, 100), (101, 99), (101, 99)])
    result, when = _find_exit(TrendContinuationBOS(), "long", 100.0, 97.0, 106.0, df, ENTRY)
    assert result.outcome == "win"
    assert when == pd.Timestamp("2026-08-27 04:00")


def test_first_hit_wins_over_later_ones():
    df = _candles([(101, 99), (101, 96), (107, 100)])  # stop first, target later
    result, when = _find_exit(TrendContinuationBOS(), "long", 100.0, 97.0, 106.0, df, ENTRY)
    assert result.outcome == "loss"
    assert when == pd.Timestamp("2026-08-26 20:00")


def test_entry_candle_itself_is_never_an_exit():
    df = _candles([(200, 50)])
    assert _find_exit(TrendContinuationBOS(), "long", 100.0, 97.0, 106.0, df, ENTRY) == (None, None)


def test_still_open_when_nothing_hit():
    df = _candles([(101, 99)] * 5)
    assert _find_exit(TrendContinuationBOS(), "long", 100.0, 97.0, 106.0, df, ENTRY) == (None, None)
