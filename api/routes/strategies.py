"""
Strategies API route -- Milestone 6. No `strategies` DB table exists yet
(see strategies/registry.py docstring) -- describes the actual code-level
strategy/parameters, not DB-persisted data.
"""

from typing import List

from fastapi import APIRouter

from api.schemas import StrategyInfoOut
from config.config import MARKET
from strategies.registry import list_strategies

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=List[StrategyInfoOut])
def get_strategies():
    return list_strategies(MARKET.pairs)
