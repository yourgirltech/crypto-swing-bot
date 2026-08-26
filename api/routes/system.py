"""
System health API route -- Milestone 6 (second batch).

Honest by construction, not just in the UI copy: `retry_events_tracked`
and `paper_engine_heartbeat_tracked` are hardcoded False in the response
itself, because this system genuinely does not persist either of those
things anywhere yet:
- okx_client.py retries transiently in-process (Milestone 0's reliability
  fix) but never writes a retry/timeout event to a table or log the API
  can read.
- paper_trading/engine.py is a separate, manually-run process
  (Milestone 4) with no heartbeat mechanism -- nothing records "the poll
  loop is alive" or "next check is scheduled for X". `latest_signal_time`
  is the best REAL proxy available (if the engine is running, it's the
  most recent time it generated a signal) -- but it's a weak proxy: the
  engine polls even when no new candle closes or no setup triggers, so a
  stale `latest_signal_time` does NOT necessarily mean the engine is down.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import SystemHealthOut
from db.models import Candle, Signal
from paper_trading.engine import POLL_INTERVAL_SECONDS

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=SystemHealthOut)
def system_health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(select(func.count()).select_from(Candle)).scalar()
    except Exception:
        db_ok = False

    latest_candle_time: Optional[datetime] = db.scalar(select(func.max(Candle.open_time)))
    latest_signal_time: Optional[datetime] = db.scalar(select(func.max(Signal.generated_at)))

    return SystemHealthOut(
        api_ok=True,
        db_ok=db_ok,
        latest_candle_time=latest_candle_time,
        latest_signal_time=latest_signal_time,
        configured_poll_interval_seconds=POLL_INTERVAL_SECONDS,
        retry_events_tracked=False,
        paper_engine_heartbeat_tracked=False,
    )
