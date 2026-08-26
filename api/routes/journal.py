"""
Journal API routes -- Milestone 5. Read-only; the journal is a query
layer over signals + paper_trades (see journal/service.py), not writable
through this API.

Route order matters: /open and /performance are registered BEFORE
/{signal_id} -- FastAPI/Starlette matches routes in registration order,
so if /{signal_id} came first, a request to /journal/open would match it
with signal_id="open" and fail int coercion (422) instead of reaching the
intended route.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import EquityPointOut, JournalEntryOut, PerformanceStatsOut
from config.config import RISK
from journal.service import (
    get_equity_curve, get_journal_entry, get_open_positions, get_performance_stats, list_journal_entries,
)

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/open", response_model=List[JournalEntryOut])
def open_positions(db: Session = Depends(get_db)):
    """Currently open paper positions -- what a Positions page needs."""
    return get_open_positions(db)


@router.get("/performance", response_model=PerformanceStatsOut)
def performance(symbol: Optional[str] = None, db: Session = Depends(get_db)):
    """Real (paper) performance from closed trades -- both ideal and realistic R, see journal.service docstring."""
    return get_performance_stats(db, symbol=symbol)


@router.get("/equity-curve", response_model=List[EquityPointOut])
def equity_curve(symbol: Optional[str] = None, db: Session = Depends(get_db)):
    """Real dollar equity curve from closed paper_trades -- see journal.service.get_equity_curve docstring."""
    return get_equity_curve(db, account_baseline=RISK.account_size_ngn, symbol=symbol)


@router.get("", response_model=List[JournalEntryOut])
def list_entries(
    symbol: Optional[str] = None,
    risk_status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
    human_decision: Optional[str] = Query(None, pattern="^(approved|declined)$"),
    outcome: Optional[str] = Query(None, pattern="^(win|loss)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Every signal ever generated, newest first -- including risk-engine-rejected and human-declined ones (see journal.service docstring on why those are kept)."""
    return list_journal_entries(
        db, symbol=symbol, risk_status=risk_status, human_decision=human_decision,
        outcome=outcome, limit=limit, offset=offset,
    )


@router.get("/{signal_id}", response_model=JournalEntryOut)
def entry_detail(signal_id: int, db: Session = Depends(get_db)):
    entry = get_journal_entry(db, signal_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No journal entry found for signal_id={signal_id}")
    return entry
