# Crypto Swing Trading Bot

A capital-preservation-first, 4H swing trading system for BTC/USDT and
ETH/USDT, currently in **paper trading** with mandatory human approval of
every trade. Full vision and milestone roadmap: [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md).
Implementation detail and every validation result: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**This bot does not promise fixed returns on a fixed timeline. No honest
trading system can.** Nothing executes without a human saying yes, and no
real capital is connected yet.

## Status (2026-09-29)

| Milestone | State |
|---|---|
| 0 - Analysis core (structure, indicators, regime, backtest, proposals) | Done |
| 1 - Postgres persistence (SQLAlchemy + Alembic) | Done |
| 2 - Risk engine with veto authority | Done |
| 3 - Strategy interface | Done |
| 4 - Paper trading engine (human-approved) | Done, running continuously via `start.cmd` |
| 5 - Journal + FastAPI | Done |
| 6 - Next.js dashboard | Done |
| 7 - Breakout / pullback / mean-reversion / range strategies | Done - none validated on BTC; Breakout validated on ETH |
| 8 - ML regime classification | Deferred - no evidence it fixes a real failure |
| 9 - Derivatives filters | Deferred - passive data collection only |
| 10 - Multi-asset | Live in paper: BTC = TrendContinuationBOS, ETH = Breakout |
| 11 - On-chain / macro context | Not started - waits on accumulated paper-trading history |
| 12 - Testnet, then ₦100k live | Not started |

## Layout

- `data/` - OKX market data client (used; Bybit is geo-blocked here) and the original Bybit client
- `structure/`, `indicators/`, `regime/` - market structure (swings, BOS/CHoCH), EMA/RSI/ATR/BB, regime labels
- `strategies/` - `Strategy` ABC plus five strategies; `registry.py` maps each symbol to its strategy
- `risk/` - `risk_engine.py` (veto gate), `position_sizing.py` (sizes down to fit caps), `status.py`
- `proposals/`, `reporting/` - trade proposal builder and plain-language trade review
- `backtest/` - walk-forward engine, held-out validation runner, combined BTC+ETH portfolio backtest
- `paper_trading/engine.py` - polls OKX every 15 min, closed 4H candles only, asks y/n before opening
- `journal/`, `api/` - journal queries and the read-only FastAPI app (port **8010**)
- `db/`, `alembic/` - models, repository, migrations
- `frontend/` - Next.js dashboard (port **3000**)
- `tests/` - pytest unit tests (risk engine, sizing, live strategies, paper-engine regressions)

## Prerequisites

- Python 3.12+, Node 20+, Docker Desktop
- **A VPN.** OKX is ISP-blocked on this network (Bybit and Binance are
  geo-blocked). Without it the engine and `main.py` get no data.

## Setup (once)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

docker compose up -d        # Postgres on host port 5433 (5432 is taken by another project)
alembic upgrade head

cd frontend; npm install; cd ..
```

## Run

```powershell
.\start.cmd              # Postgres + backend :8010 + frontend :3000 + paper trading engine
.\start.cmd -NoEngine    # same, without the engine
.\stop.cmd               # stops backend, frontend and engine (Postgres keeps running)
```

Each server opens in its own window. The **paper engine window is where
trade approvals appear** (the console beeps). Leave it open for the
engine to keep running. It restarts itself if the process dies, and a
proposal waits in that window until you answer it. Anything already
running is left alone, so re-running `start.cmd` is safe. The backend's
first start can take 1-2 minutes (slow imports from the OneDrive folder).

- Dashboard: http://localhost:3000
- API docs: http://localhost:8010/docs

Other entry points:

```powershell
python main.py                                            # one-shot backtest + current proposal, persisted
python -m backtest.validate_milestone7 --symbol=ETHUSDT breakout   # full / in-sample / held-out validation
python -m pytest                                          # unit tests
```

## Configuration

All risk, pair and strategy parameters live in `config/config.py`. Risk
limits there were each derived from backtest data (see the comments next
to each value). Change them deliberately, never to make a trade fit.

## Explicitly out of scope right now

- Intraday/scalping timeframes
- Leverage (capped at 1x)
- Unattended or auto-approved execution
- Any guaranteed or fixed-timeline return target
