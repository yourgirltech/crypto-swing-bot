"""
System health API route -- Milestone 6, instrumented with genuine
retry/heartbeat tracking (replacing the original hardcoded-False fields
now that data/okx_client.py and paper_trading/engine.py actually write
to retry_events/engine_heartbeats -- see db/models.py).

Thresholds below are deliberate, stated choices, not magic numbers:
- RETRY_LOOKBACK_MINUTES / RETRY_ELEVATED_THRESHOLD: a handful of
  isolated retries is exactly what the retry-with-backoff logic
  (Milestone 0) is FOR -- normal, not a problem. "Elevated" means a
  genuinely unusual CURRENT burst (more than 5 retries in the last hour),
  not historical noise from days ago.
- HEARTBEAT_STALE_MULTIPLIER: the engine polls every
  POLL_INTERVAL_SECONDS (900s/15min). A single slow cycle (e.g. one that
  hit an OKX retry) shouldn't immediately read as "stale" -- 2x the
  interval (30 min) gives one full cycle's worth of slack before
  flagging it. Beyond 24h with no heartbeat, "stale" becomes
  "not_running" -- at that point it's not a slow cycle, the process
  almost certainly isn't running at all.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import SystemHealthOut
from db.models import Candle, Signal
from db.repository import count_retry_events_since, get_latest_heartbeat, list_recent_retry_events
from paper_trading.engine import ENGINE_NAME, POLL_INTERVAL_SECONDS

router = APIRouter(prefix="/system", tags=["system"])

RETRY_LOOKBACK_MINUTES = 60
RETRY_ELEVATED_THRESHOLD = 5
HEARTBEAT_STALE_MULTIPLIER = 2


@router.get("/health", response_model=SystemHealthOut)
def system_health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(select(func.count()).select_from(Candle)).scalar()
    except Exception:
        db_ok = False

    latest_candle_time: Optional[datetime] = db.scalar(select(func.max(Candle.open_time)))
    latest_signal_time: Optional[datetime] = db.scalar(select(func.max(Signal.generated_at)))
    now = datetime.utcnow()

    # --- Retry tracking (real, from retry_events) ---
    recent_events = list_recent_retry_events(db, limit=20)
    retry_count_recent = count_retry_events_since(db, now - timedelta(minutes=RETRY_LOOKBACK_MINUTES))
    retry_health = "elevated" if retry_count_recent > RETRY_ELEVATED_THRESHOLD else "clean"

    # --- Paper engine heartbeat (real, from engine_heartbeats) ---
    latest_heartbeat = get_latest_heartbeat(db, ENGINE_NAME)
    stale_threshold = timedelta(seconds=POLL_INTERVAL_SECONDS * HEARTBEAT_STALE_MULTIPLIER)
    stale_threshold_minutes = POLL_INTERVAL_SECONDS * HEARTBEAT_STALE_MULTIPLIER / 60

    if latest_heartbeat is None:
        paper_engine_status = "not_running"
        paper_engine_detail = (
            "No heartbeat has ever been recorded — the paper trading engine has not "
            "been run since this tracking was added."
        )
        latest_heartbeat_at = None
    else:
        latest_heartbeat_at = latest_heartbeat.checked_in_at
        elapsed = now - latest_heartbeat_at
        elapsed_minutes = elapsed.total_seconds() / 60
        if elapsed <= stale_threshold:
            paper_engine_status = "running"
            paper_engine_detail = f"Last checked in {elapsed_minutes:.1f} min ago (symbol {latest_heartbeat.symbol})."
        elif elapsed <= timedelta(hours=24):
            paper_engine_status = "stale"
            paper_engine_detail = (
                f"Last checked in {elapsed_minutes:.1f} min ago — expected within "
                f"{stale_threshold_minutes:.0f} min ({HEARTBEAT_STALE_MULTIPLIER}x the "
                f"{POLL_INTERVAL_SECONDS}s poll interval) and hasn't checked in since."
            )
        else:
            paper_engine_status = "not_running"
            paper_engine_detail = f"Last checked in {elapsed_minutes / 60:.1f} hours ago — not currently running."

    return SystemHealthOut(
        api_ok=True,
        db_ok=db_ok,
        latest_candle_time=latest_candle_time,
        latest_signal_time=latest_signal_time,
        configured_poll_interval_seconds=POLL_INTERVAL_SECONDS,
        retry_events_tracked=True,
        paper_engine_heartbeat_tracked=True,
        recent_retry_events=recent_events,
        retry_count_recent=retry_count_recent,
        retry_lookback_minutes=RETRY_LOOKBACK_MINUTES,
        retry_elevated_threshold=RETRY_ELEVATED_THRESHOLD,
        retry_health=retry_health,
        paper_engine_status=paper_engine_status,
        paper_engine_detail=paper_engine_detail,
        latest_heartbeat_at=latest_heartbeat_at,
        heartbeat_stale_threshold_minutes=stale_threshold_minutes,
    )
