"""
Backtest history API routes -- Milestone 6. Read-only, over PERSISTED
backtest_runs/backtest_trades (backtest/history.py) -- does not run a
fresh backtest on request (that's expensive; see main.py for that path).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import BacktestRunOut, CumulativeRPointOut
from backtest.history import get_backtest_run, get_cumulative_r_curve, list_backtest_runs

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("", response_model=List[BacktestRunOut])
def list_runs(
    symbol: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return list_backtest_runs(db, symbol=symbol, limit=limit)


@router.get("/{run_id}", response_model=BacktestRunOut)
def run_detail(run_id: int, db: Session = Depends(get_db)):
    run = get_backtest_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No backtest run found for run_id={run_id}")
    return run


@router.get("/{run_id}/cumulative-r", response_model=List[CumulativeRPointOut])
def run_cumulative_r(run_id: int, db: Session = Depends(get_db)):
    """Cumulative R-multiple curve, NOT a dollar equity curve -- see backtest.history's module docstring for why."""
    points = get_cumulative_r_curve(db, run_id)
    if points is None:
        raise HTTPException(status_code=404, detail=f"No backtest run found for run_id={run_id}")
    return points
