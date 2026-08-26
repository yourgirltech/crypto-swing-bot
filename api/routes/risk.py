"""
Risk status API route -- Milestone 6 (second batch). Read-only snapshot of
the risk engine's current standing against every configured limit --
"is the guardrail actually working" (see risk/status.py).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import RiskStatusOut
from config.config import RISK
from risk.status import get_risk_status

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status", response_model=RiskStatusOut)
def risk_status(db: Session = Depends(get_db)):
    return get_risk_status(db, RISK)
