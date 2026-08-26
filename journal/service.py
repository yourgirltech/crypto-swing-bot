"""
Trading journal -- Milestone 5.

The journal is deliberately NOT a new table. Every trade's full lifecycle
-- proposal, risk verdict, human decision, fill, exit, realized P&L -- is
already captured across `signals` (Milestone 2/4) and `paper_trades`
(Milestone 4), linked 1:1 via `paper_trades.signal_id`. Duplicating that
into a new `journal` table would create two sources of truth for the same
data (exactly the kind of duplication Milestone 3 removed for entry/stop/
target logic, and Milestone 4 removed for sizing) -- this module is a
QUERY layer composing the two, exposed through FastAPI (api/routes/
journal.py) as the contract Milestone 6's frontend will consume.

A JournalEntry always exists for every Signal, even one the risk engine
REJECTED or a human DECLINED -- the paper_trade_* fields are simply None
in that case. This is deliberate: the "why didn't we take this trade"
record is as much a part of the journal as executed trades are, matching
the project's existing transparency principle (never hide the reasoning
behind a decision, including a non-decision).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Asset, HumanDecision, PaperTrade, PaperTradeStatus, Signal, SignalStatus


@dataclass
class JournalEntry:
    """One trade's full lifecycle: Signal (proposal + risk verdict + human decision) + PaperTrade (fill + exit + realized P&L), when one exists."""
    signal_id: int
    symbol: str
    generated_at: datetime
    triggering_candle_time: datetime

    setup_type: str
    direction: str
    trend: str
    regime: str
    rsi: float
    entry_price: float
    stop_price: float
    target_price: float
    reward_risk_ratio: float
    risk_amount: float
    position_size: float
    backtested_win_rate_pct: Optional[float]
    backtested_sample_size: Optional[int]
    backtested_expectancy_r: Optional[float]
    notes: str

    risk_status: str                       # SignalStatus value: "approved" | "rejected"
    risk_verdict_reason: Optional[str]
    human_decision: Optional[str]          # HumanDecision value, or None if never reached a human
    human_decision_reason: Optional[str]
    human_decision_at: Optional[datetime]

    # Populated only if a PaperTrade exists (risk engine AND human both approved):
    paper_trade_id: Optional[int] = None
    paper_trade_status: Optional[str] = None   # "open" | "closed"
    data_source: Optional[str] = None
    entry_fill_price: Optional[float] = None
    entry_fee: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    proposed_exit_price: Optional[float] = None
    exit_fill_price: Optional[float] = None
    exit_fee: Optional[float] = None
    outcome: Optional[str] = None              # "win" | "loss"
    r_multiple_ideal: Optional[float] = None
    r_multiple_realistic: Optional[float] = None
    pnl_ngn: Optional[float] = None


def _to_entry(signal: Signal) -> JournalEntry:
    pt = signal.paper_trade
    return JournalEntry(
        signal_id=signal.id,
        symbol=signal.asset.symbol,
        generated_at=signal.generated_at,
        triggering_candle_time=signal.triggering_candle_time,
        setup_type=signal.setup_type,
        direction=signal.direction,
        trend=signal.trend,
        regime=signal.regime,
        rsi=signal.rsi,
        entry_price=signal.entry_price,
        stop_price=signal.stop_price,
        target_price=signal.target_price,
        reward_risk_ratio=signal.reward_risk_ratio,
        risk_amount=signal.risk_amount,
        position_size=signal.position_size,
        backtested_win_rate_pct=signal.backtested_win_rate_pct,
        backtested_sample_size=signal.backtested_sample_size,
        backtested_expectancy_r=signal.backtested_expectancy_r,
        notes=signal.notes,
        risk_status=signal.status.value,
        risk_verdict_reason=signal.risk_verdict_reason,
        human_decision=signal.human_decision.value if signal.human_decision else None,
        human_decision_reason=signal.human_decision_reason,
        human_decision_at=signal.human_decision_at,
        paper_trade_id=pt.id if pt else None,
        paper_trade_status=pt.status.value if pt else None,
        data_source=pt.data_source if pt else None,
        entry_fill_price=pt.entry_fill_price if pt else None,
        entry_fee=pt.entry_fee if pt else None,
        entry_time=pt.entry_time if pt else None,
        exit_time=pt.exit_time if pt else None,
        proposed_exit_price=pt.proposed_exit_price if pt else None,
        exit_fill_price=pt.exit_fill_price if pt else None,
        exit_fee=pt.exit_fee if pt else None,
        outcome=pt.outcome if pt else None,
        r_multiple_ideal=pt.r_multiple_ideal if pt else None,
        r_multiple_realistic=pt.r_multiple_realistic if pt else None,
        pnl_ngn=pt.pnl_ngn if pt else None,
    )


def list_journal_entries(session: Session, symbol: Optional[str] = None,
                          risk_status: Optional[str] = None,
                          human_decision: Optional[str] = None,
                          outcome: Optional[str] = None,
                          limit: int = 100, offset: int = 0) -> List[JournalEntry]:
    """
    Newest first. `outcome` filters on the linked PaperTrade's outcome (so
    it implicitly excludes signals with no paper trade) -- applied after
    the query since it depends on the related row, not a Signal column.
    """
    stmt = select(Signal).join(Asset).order_by(Signal.generated_at.desc())
    if symbol:
        stmt = stmt.where(Asset.symbol == symbol)
    if risk_status:
        stmt = stmt.where(Signal.status == SignalStatus(risk_status))
    if human_decision:
        stmt = stmt.where(Signal.human_decision == HumanDecision(human_decision))
    stmt = stmt.limit(limit).offset(offset)

    signals = session.scalars(stmt).all()
    entries = [_to_entry(s) for s in signals]
    if outcome:
        entries = [e for e in entries if e.outcome == outcome]
    return entries


def get_journal_entry(session: Session, signal_id: int) -> Optional[JournalEntry]:
    signal = session.get(Signal, signal_id)
    return _to_entry(signal) if signal else None


def get_open_positions(session: Session) -> List[JournalEntry]:
    """Signals whose linked PaperTrade is still OPEN -- what a Positions page needs."""
    stmt = (
        select(Signal)
        .join(PaperTrade, PaperTrade.signal_id == Signal.id)
        .where(PaperTrade.status == PaperTradeStatus.OPEN)
        .order_by(PaperTrade.entry_time.desc())
    )
    signals = session.scalars(stmt).all()
    return [_to_entry(s) for s in signals]


@dataclass
class PerformanceStats:
    total_closed_trades: int
    win_rate_pct: float
    avg_win_r_realistic: float
    avg_loss_r_realistic: float
    expectancy_r_ideal: float          # naive backtest-style R (-1.0 / +reward_risk), see Milestone 4
    expectancy_r_realistic: float      # after simulated slippage + fees
    total_pnl_ngn: float
    total_fees_ngn: float


def get_performance_stats(session: Session, symbol: Optional[str] = None) -> PerformanceStats:
    """
    Real (paper) performance from closed paper_trades, not the backtest --
    the whole point of tracking BOTH r_multiple_ideal and r_multiple_realistic
    (Milestone 4) is to see how far live-simulated execution actually drifts
    from the naive backtest assumption; both are reported here so that
    comparison is visible, not just the realistic number in isolation.
    """
    stmt = select(PaperTrade).where(PaperTrade.status == PaperTradeStatus.CLOSED)
    if symbol:
        stmt = stmt.join(Asset).where(Asset.symbol == symbol)
    trades = session.scalars(stmt).all()

    if not trades:
        return PerformanceStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [t for t in trades if t.outcome == "win"]
    losses = [t for t in trades if t.outcome == "loss"]
    total_fees = sum((t.entry_fee or 0.0) + (t.exit_fee or 0.0) for t in trades)

    return PerformanceStats(
        total_closed_trades=len(trades),
        win_rate_pct=round(len(wins) / len(trades) * 100, 1),
        avg_win_r_realistic=round(sum(t.r_multiple_realistic for t in wins) / len(wins), 3) if wins else 0.0,
        avg_loss_r_realistic=round(sum(t.r_multiple_realistic for t in losses) / len(losses), 3) if losses else 0.0,
        expectancy_r_ideal=round(sum(t.r_multiple_ideal for t in trades) / len(trades), 3),
        expectancy_r_realistic=round(sum(t.r_multiple_realistic for t in trades) / len(trades), 3),
        total_pnl_ngn=round(sum(t.pnl_ngn for t in trades), 2),
        total_fees_ngn=round(total_fees, 2),
    )


@dataclass
class EquityPoint:
    time: datetime
    equity: float
    pnl_ngn: float
    symbol: str
    outcome: str


def get_equity_curve(session: Session, account_baseline: float, symbol: Optional[str] = None) -> List[EquityPoint]:
    """
    REAL dollar equity curve reconstructed from closed paper_trades, in
    exit order -- unlike backtest_trades (see backtest/history.py), a
    PaperTrade's position_size/risk_amount/pnl_ngn ARE persisted (Milestone
    4), so this is dollar-accurate, not an approximation. Starts with one
    point at account_baseline so the chart has a defined starting value
    even before any trade has closed.
    """
    stmt = select(PaperTrade).where(PaperTrade.status == PaperTradeStatus.CLOSED).order_by(PaperTrade.exit_time)
    if symbol:
        stmt = stmt.join(Asset).where(Asset.symbol == symbol)
    trades = session.scalars(stmt).all()

    equity = account_baseline
    points = [EquityPoint(time=trades[0].entry_time if trades else datetime.utcnow(),
                           equity=equity, pnl_ngn=0.0, symbol="", outcome="start")]
    for t in trades:
        equity += t.pnl_ngn
        points.append(EquityPoint(
            time=t.exit_time, equity=round(equity, 2), pnl_ngn=round(t.pnl_ngn, 2),
            symbol=t.asset.symbol, outcome=t.outcome,
        ))
    return points
