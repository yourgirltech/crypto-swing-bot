"""
Market data API route -- Milestone 6 charting. Serves PERSISTED candles
(Milestone 1) with indicators recomputed on demand via indicators.py --
the SAME function the strategy/backtest actually use, so the EMA lines
shown are the real thing the bot reasons about, not a lookalike.

Historical, not live: this project polls OKX on an interval rather than
streaming (Milestone 4's deliberate decision). This endpoint serves
whatever was last persisted to `candles` as of the last poll/backtest
run -- not a continuously-updating real-time feed. There is no
real-time price stream in this system yet.
"""

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import CandleOut
from db.models import Asset, Candle
from indicators.indicators import add_all_indicators

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/candles", response_model=List[CandleOut])
def get_candles(
    symbol: str,
    timeframe: str = "240",
    source: str = "okx",
    limit: int = Query(300, ge=10, le=2000),
    db: Session = Depends(get_db),
):
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None:
        return []

    rows = db.scalars(
        select(Candle)
        .where(Candle.asset_id == asset.id, Candle.timeframe == timeframe, Candle.source == source)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))  # chronological order for charting
    if not rows:
        return []

    df = pd.DataFrame([{
        "open_time": r.open_time, "open": r.open, "high": r.high, "low": r.low,
        "close": r.close, "volume": r.volume, "turnover": r.turnover,
    } for r in rows])
    df = add_all_indicators(df, ema_fast=21, ema_slow=50, rsi_period=14, atr_period=14)

    return [
        CandleOut(
            open_time=row.open_time,
            open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close),
            ema_fast=float(row.ema_21) if pd.notna(row.ema_21) else None,
            ema_slow=float(row.ema_50) if pd.notna(row.ema_50) else None,
            rsi=float(row.rsi) if pd.notna(row.rsi) else None,
        )
        for row in df.itertuples(index=False)
    ]
