"""
Query + aggregate PERSISTED backtest history -- Milestone 6.

Distinct from backtest_engine.py, which RUNS a fresh backtest; this only
reads what's already in Postgres (backtest_runs/backtest_trades,
Milestone 1) for the API to expose to the Backtesting page.

Honest limitation, not silently smoothed over: max_drawdown_pct is NOT
reconstructable from persisted backtest_trades rows -- BacktestTrade never
stored per-trade position_size/risk_amount (Milestone 4's sizing fix added
those to the in-memory Trade dataclass, not the DB schema), and drawdown
requires an equity curve that depends on exactly that. Approximating one
from r_multiple alone (e.g. assuming equal position sizing) would produce
a number that doesn't match what the original run actually computed --
this module omits it entirely for historical runs rather than fabricate
an approximation, consistent with this project's "never invent a number
we don't have real data for" rule (see proposals/trade_proposal.py).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Asset, BacktestRun, BacktestTrade


@dataclass
class BacktestSummary:
    total_trades: int
    win_rate_pct: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float


@dataclass
class RegimeStats:
    regime: str
    trades: int
    win_rate_pct: float
    expectancy_r: float


def _summarize(trades: List[BacktestTrade]) -> BacktestSummary:
    closed = [t for t in trades if t.outcome in ("win", "loss")]
    if not closed:
        return BacktestSummary(0, 0.0, 0.0, 0.0, 0.0)
    wins = [t.r_multiple for t in closed if t.outcome == "win"]
    losses = [t.r_multiple for t in closed if t.outcome == "loss"]
    return BacktestSummary(
        total_trades=len(closed),
        win_rate_pct=round(len(wins) / len(closed) * 100, 1),
        avg_win_r=round(sum(wins) / len(wins), 2) if wins else 0.0,
        avg_loss_r=round(sum(losses) / len(losses), 2) if losses else 0.0,
        expectancy_r=round(sum(t.r_multiple for t in closed) / len(closed), 3),
    )


def _by_regime(trades: List[BacktestTrade]) -> List[RegimeStats]:
    closed = [t for t in trades if t.outcome in ("win", "loss")]
    grouped: Dict[str, List[BacktestTrade]] = {}
    for t in closed:
        grouped.setdefault(t.regime or "unknown", []).append(t)
    out = []
    for regime, group in grouped.items():
        wins = sum(1 for t in group if t.outcome == "win")
        out.append(RegimeStats(
            regime=regime,
            trades=len(group),
            win_rate_pct=round(wins / len(group) * 100, 1),
            expectancy_r=round(sum(t.r_multiple for t in group) / len(group), 3),
        ))
    return sorted(out, key=lambda r: r.expectancy_r, reverse=True)


@dataclass
class BacktestRunOut:
    id: int
    symbol: str
    timeframe: str
    run_at: object
    data_source: str
    date_range_start: object
    date_range_end: object
    params: dict
    summary: BacktestSummary
    regime_breakdown: List[RegimeStats] = field(default_factory=list)


def list_backtest_runs(session: Session, symbol: Optional[str] = None, limit: int = 50) -> List[BacktestRunOut]:
    """Newest first, summary only (no regime breakdown -- see get_backtest_run for full detail)."""
    stmt = select(BacktestRun).join(Asset).order_by(BacktestRun.run_at.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(Asset.symbol == symbol)
    runs = session.scalars(stmt).all()
    return [
        BacktestRunOut(
            id=r.id, symbol=r.asset.symbol, timeframe=r.timeframe, run_at=r.run_at,
            data_source=r.data_source, date_range_start=r.date_range_start,
            date_range_end=r.date_range_end, params=r.params, summary=_summarize(r.trades),
        )
        for r in runs
    ]


def get_backtest_run(session: Session, run_id: int) -> Optional[BacktestRunOut]:
    run = session.get(BacktestRun, run_id)
    if run is None:
        return None
    return BacktestRunOut(
        id=run.id, symbol=run.asset.symbol, timeframe=run.timeframe, run_at=run.run_at,
        data_source=run.data_source, date_range_start=run.date_range_start,
        date_range_end=run.date_range_end, params=run.params,
        summary=_summarize(run.trades), regime_breakdown=_by_regime(run.trades),
    )


@dataclass
class CumulativeRPoint:
    time: object          # entry_time of the trade that closed this point
    r_multiple: float      # this trade's own R
    cumulative_r: float    # running sum -- NOT a dollar equity curve, see module docstring
    outcome: str
    direction: str


def get_cumulative_r_curve(session: Session, run_id: int) -> Optional[List[CumulativeRPoint]]:
    """
    Cumulative R-multiple across a run's trades, in entry order. Deliberately
    NOT a dollar equity curve -- see module docstring: position size/risk
    amount were never persisted per backtest_trades row, so a dollar figure
    here would not match what the original run actually computed. R-multiple
    is position-size-independent by construction, so this IS an honest,
    exact reconstruction of the run's trade-by-trade R sequence.
    """
    run = session.get(BacktestRun, run_id)
    if run is None:
        return None
    closed = sorted(
        (t for t in run.trades if t.outcome in ("win", "loss")),
        key=lambda t: t.entry_time,
    )
    points = []
    cumulative = 0.0
    for t in closed:
        cumulative += t.r_multiple
        points.append(CumulativeRPoint(
            time=t.entry_time, r_multiple=t.r_multiple, cumulative_r=round(cumulative, 3),
            outcome=t.outcome, direction=t.direction,
        ))
    return points
