"""
Bybit data client — pulls OHLCV via the public v5 market/kline endpoint.
No API key required for historical/public market data.
"""

import time
import requests
import pandas as pd

BASE_URL_MAINNET = "https://api.bybit.com"
BASE_URL_TESTNET = "https://api-testnet.bybit.com"


class BybitClient:
    def __init__(self, testnet: bool = True, category: str = "spot"):
        self.base_url = BASE_URL_TESTNET if testnet else BASE_URL_MAINNET
        self.category = category

    def get_klines(self, symbol: str, interval: str, limit: int = 1000,
                    start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
        """
        Fetch OHLCV klines.
        interval: Bybit kline interval string, e.g. "240" (4H), "D" (daily).
        Returns a DataFrame sorted ascending by time, columns:
        [open_time, open, high, low, close, volume, turnover]
        """
        url = f"{self.base_url}/v5/market/kline"
        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_ms:
            params["start"] = start_ms
        if end_ms:
            params["end"] = end_ms

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {payload.get('retMsg')}")

        rows = payload["result"]["list"]
        if not rows:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])

        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])
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
        Bybit returns max 1000 candles per call, so we walk back in time.
        """
        interval_minutes = {"D": 1440, "240": 240, "60": 60, "15": 15}.get(interval, 240)
        total_candles_needed = int((days * 1440) / interval_minutes)

        all_frames = []
        end_ms = int(time.time() * 1000)
        remaining = total_candles_needed

        while remaining > 0:
            batch = min(remaining, 1000)
            df = self.get_klines(symbol, interval, limit=batch, end_ms=end_ms)
            if df.empty:
                break
            all_frames.append(df)
            earliest = df["open_time"].min()
            end_ms = int(earliest.timestamp() * 1000) - 1
            remaining -= len(df)
            if len(df) < batch:
                break
            time.sleep(0.1)  # be polite to the API

        if not all_frames:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "turnover"])

        result = pd.concat(all_frames, ignore_index=True)
        result = result.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
        return result
