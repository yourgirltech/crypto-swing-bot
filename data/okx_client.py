"""
OKX data client — drop-in replacement for BybitClient (same interface,
same DataFrame return shape).

Why this exists: Bybit's public API is geo-blocked from this machine
(HTTP 403 CloudFront) and Binance is also blocked (HTTP 451). OKX's
public market-data API is used here for BACKTESTING historical data
only. Bybit remains the documented execution exchange per docs/.
No API key required — this hits OKX's public candles endpoint.

Milestone 6: every failed attempt inside the retry loop below is logged
to `retry_events` (db.repository.record_retry_event) for the System
Health page — best-effort, via `_log_retry_event()`, which swallows any
error of its own. Logging a retry must never be able to break the actual
retry it's trying to record.
"""

import time
import requests
import pandas as pd


def _log_retry_event(request_desc: str, attempt_number: int, max_attempts: int,
                      delay_seconds: float, exc: Exception) -> None:
    """
    Best-effort persistence of one retry attempt. Deliberately swallows
    every exception of its own (including "DB isn't reachable") -- a
    logging failure must never break the actual data-fetching retry it's
    trying to record. Imports are local so importing okx_client.py itself
    never requires the DB layer to be importable/configured.
    """
    try:
        from db.session import get_session
        from db.repository import record_retry_event
        with get_session() as session:
            record_retry_event(
                session, source="okx", request_desc=request_desc,
                attempt_number=attempt_number, max_attempts=max_attempts,
                delay_seconds=delay_seconds,
                exception_type=type(exc).__name__, exception_message=str(exc),
            )
    except Exception:
        pass

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


def _to_okx_perp_symbol(symbol: str) -> str:
    """
    BTCUSDT -> BTC-USDT-SWAP -- the perpetual swap instId, distinct from
    the spot instId get_klines uses. Funding rate / open interest /
    long-short ratio are perpetual-swap-specific concepts that don't
    exist for the spot instrument this project actually trades (see
    Milestone 9 -- these are collected as passive CONTEXT data alongside
    spot trades, not traded themselves).
    """
    return f"{_to_okx_symbol(symbol)}-SWAP"


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
        request_desc = f"GET klines {symbol} {interval}"
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                break
            except (requests.exceptions.RequestException,) as exc:
                if attempt == max_retries - 1:
                    _log_retry_event(request_desc, attempt + 1, max_retries, 0.0, exc)
                    raise
                backoff = 2 ** attempt  # 1s, 2s, 4s
                _log_retry_event(request_desc, attempt + 1, max_retries, backoff, exc)
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

    # -- Milestone 9 (deferred as a live feature -- see docs/ARCHITECTURE.md).
    # These three back paper_trading/engine.py's passive derivatives-
    # collection step ONLY -- nothing else in this codebase calls them.
    # Deliberately no retry-with-backoff here (unlike get_klines): this is
    # non-critical context data, not a fetch the core trading logic
    # depends on, so a single failed attempt just means one poll cycle's
    # snapshot is skipped (there's another one in 15 minutes) rather than
    # adding latency to every cycle for a non-essential value. Each
    # returns None on any failure -- the caller treats that as "skip this
    # field," not an error to propagate.

    def get_funding_rate(self, symbol: str) -> float | None:
        """Current funding rate for symbol's perpetual swap."""
        inst_id = _to_okx_perp_symbol(symbol)
        try:
            resp = requests.get(f"{self.base_url}/api/v5/public/funding-rate",
                                 params={"instId": inst_id}, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0" or not payload.get("data"):
                return None
            return float(payload["data"][0]["fundingRate"])
        except Exception:
            return None

    def get_open_interest(self, symbol: str) -> float | None:
        """Current open interest (in the instrument's own coin unit, oiCcy) for symbol's perpetual swap."""
        inst_id = _to_okx_perp_symbol(symbol)
        try:
            resp = requests.get(f"{self.base_url}/api/v5/public/open-interest",
                                 params={"instType": "SWAP", "instId": inst_id}, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0" or not payload.get("data"):
                return None
            return float(payload["data"][0]["oiCcy"])
        except Exception:
            return None

    def get_long_short_ratio(self, symbol: str) -> float | None:
        """Current long/short account ratio for symbol's perpetual swap (>1 means more long accounts than short)."""
        inst_id = _to_okx_perp_symbol(symbol)
        try:
            resp = requests.get(
                f"{self.base_url}/api/v5/rubik/stat/contracts/long-short-account-ratio-contract",
                params={"instId": inst_id, "period": "5m", "limit": 1}, timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0" or not payload.get("data"):
                return None
            return float(payload["data"][0][1])
        except Exception:
            return None
