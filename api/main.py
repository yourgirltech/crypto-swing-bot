"""
FastAPI app -- Milestone 5/6. Exposes the trading journal (signals +
paper_trades), persisted backtest history, and the strategy registry as
the API contract Milestone 6's Next.js dashboard consumes.

Run with: uvicorn api.main:app --reload --port 8010
Docs then at: http://localhost:8010/docs

Port 8010, not the more obvious 8000: this machine also runs a separate,
unrelated project (Clyra) whose backend defaults to 8000 -- discovered by
a live port collision while testing this milestone. Keep 8010 as this
project's convention rather than reclaiming 8000, since both projects can
then run simultaneously without a fight over the port.

CORS allows the Next.js dev server's default origin only (localhost:3000)
-- this is a local single-user dashboard, not a public API, so there is
no reason to allow "*" here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.account import router as account_router
from api.routes.backtests import router as backtests_router
from api.routes.journal import router as journal_router
from api.routes.market import router as market_router
from api.routes.risk import router as risk_router
from api.routes.strategies import router as strategies_router
from api.routes.system import router as system_router

app = FastAPI(
    title="Crypto Swing Bot API",
    version="0.2.0",
    description="Read-only API over signals/paper_trades (journal), backtest_runs (backtests), and the strategy registry.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(journal_router)
app.include_router(backtests_router)
app.include_router(strategies_router)
app.include_router(account_router)
app.include_router(market_router)
app.include_router(risk_router)
app.include_router(system_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
