"""
Account/portfolio summary API route -- Milestone 6. Reuses
db.repository.build_portfolio_state() (Milestone 2/4) directly rather than
recomputing equity from scratch elsewhere -- one source of truth for
"current account state," the same function the risk engine itself uses.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import AccountSummaryOut
from config.config import RISK
from db.repository import build_portfolio_state

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountSummaryOut)
def get_account_summary(db: Session = Depends(get_db)):
    portfolio = build_portfolio_state(db, account_baseline=RISK.account_size_ngn)
    return AccountSummaryOut(
        account_baseline=RISK.account_size_ngn,
        account_equity=portfolio.account_equity,
        peak_equity=portfolio.peak_equity,
        open_positions_count=len(portfolio.open_positions),
        daily_pnl_pct=portfolio.daily_pnl_pct,
        weekly_pnl_pct=portfolio.weekly_pnl_pct,
        max_daily_loss_pct=RISK.max_daily_loss_pct,
        max_weekly_loss_pct=RISK.max_weekly_loss_pct,
        max_open_positions=RISK.max_open_positions,
        max_drawdown_pct=RISK.max_drawdown_pct,
    )
