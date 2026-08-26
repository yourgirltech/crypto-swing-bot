"""
OKX data client — drop-in replacement for BybitClient (same interface,
same DataFrame return shape).

Why this exists: Bybit's public API is geo-blocked from this machine
(HTTP 403 CloudFront) and Binance is also blocked (HTTP 451). OKX's
public market-data API is used here for BACKTESTING historical data
only. Bybit remains the documented execution exchange per docs/.
No API key required — this hits OKX's public candles endpoint.
"""

import time
import requests
import pandas as pd

BASE_URL = "https://www.okx.com"

# Bybit-style interval strings (used elsewhere in this repo, e.g. config.py)
# translated to OKX's bar format.
_BAR_MAP = {
    "D": "1D",
    "1D": "1D",
    "240": "4H",
    "60": "1H",
    "15": "15m",
    "5": "5m",
    "1": "1m",
}

_INTERVAL_MINUTES = {"D": 1440, "240": 240, "60": 60, "15": 15}


def _to_okx_symbol(symbol: str) -> str:
    """BTCUSDT -> BTC-USDT"""
    for quote in ("USDT", "USDC", "USD"):
        if symbol.endswith(quote):
            return f"{symbol[:-len(quote)]}-{quote}"
    return symbol


class OKXClient:
    """Same interface/return shape as BybitClient, backed by OKX's public API."""

    def __init__(self, testnet: bool = True, category: str = "spot"):
        # OKX public market data doesn't distinguish testnet/category;
        # params kept for interface compatibility with BybitClient.
        self.base_url = BASE_URL
        self.category = category

    def get_klines(self, symbol: str, interval: str, limit: int = 1000,
                    start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
        """
        Fetch OHLCV klines via OKX's history-candles endpoint.
        interval: Bybit-style interval string, e.g. "240" (4H), "D" (daily).
        Returns a DataFrame sorted ascending by time, columns:
        [open_time, open, high, low, close, volume, turnover]
        """
        bar = _BAR_MAP.get(interval, "4H")
        inst_id = _to_okx_symbol(symbol)
        url = f"{self.base_url}/api/v5/market/history-candles"
        params = {
            "instId": inst_id,
            "bar": bar,
            "limit": min(limit, 100),  # OKX history-candles caps at 100/call
        }
        if end_ms:
            params["after"] = end_ms    # OKX convention: "after" = records earlier than ts
        if start_ms:
            params["before"] = start_ms  # OKX convention: "before" = records newer than ts

        max_retries = 4
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                break
            except (requests.exceptions.RequestException,) as exc:
                if attempt == max_retries - 1:
                    raise
                backoff = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(backoff)

        if payload.get("code") != "0":
            raise RuntimeError(f"OKX API error: {payload.get('msg')}")

        rows = payload["data"]
        if not rows:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])

        # OKX rows: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm] — take first 6
        trimmed = [row[:6] for row in rows]
        df = pd.DataFrame(trimmed, columns=["open_time", "open", "high", "low", "close", "volume"])
        df["turnover"] = df["volume"]
        df = df.astype({
            "open_time": "int64", "open": "float64", "high": "float64",
            "low": "float64", "close": "float64", "volume": "float64", "turnover": "float64",
        })
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.sort_values("open_time").reset_index(drop=True)
        return df

    def get_historical_klines(self, symbol: str, interval: str, days: int) -> pd.DataFrame:
        """
        Paginate backwards to assemble `days` worth of history.
        OKX returns max 100 candles per history-candles call, so we walk
        back in time using the "after" cursor.
        """
        interval_minutes = _INTERVAL_MINUTES.get(interval, 240)
        total_candles_needed = int((days * 1440) / interval_minutes)

        all_frames = []
        end_ms = int(time.time() * 1000)
        remaining = total_candles_needed

        while remaining > 0:
            batch = min(remaining, 100)
            df = self.get_klines(symbol, interval, limit=batch, end_ms=end_ms)
            if df.empty:
                break
            all_frames.append(df)
            earliest = df["open_time"].min()
            end_ms = int(earliest.timestamp() * 1000) - 1
            remaining -= len(df)
            if len(df) < batch:
                break
            time.sleep(0.15)  # be polite to the API

        if not all_frames:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])

        result = pd.concat(all_frames, ignore_index=True)
        result = result.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
        return result
