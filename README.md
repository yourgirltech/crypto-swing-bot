# Crypto Swing Trading Bot (Phase 1)

A capital-preservation-first, swing-timeframe trading bot for Bybit
(BTC/USDT, ETH/USDT). Full design rationale and phased roadmap in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — read that first.

**This bot does not promise fixed returns on a fixed timeline. No honest
trading system can.** The goal is steady, risk-controlled growth with
capital preservation as the top priority. Every trade requires human
approval — nothing executes automatically in this phase.

## What's implemented (Phase 1)

- `data/` — Bybit OHLCV ingestion (public endpoint, no API key needed for historical data)
- `structure/` — deterministic market structure engine: swing highs/lows,
  HH/HL/LH/LL trend sequencing, BOS/CHoCH detection, support/resistance
  zones, equal-high/low liquidity clusters, session/prior-day levels
- `indicators/` — lean confluence stack: EMA trend filter, RSI, ATR,
  Bollinger Bands
- `regime/` — regime classifier (strong bull / weak bull / range /
  hyperbolic / strong bear / panic recovery), every label traceable to
  the underlying numbers
- `backtest/` — walk-forward backtest engine producing real win-rate,
  expectancy, and drawdown stats — the source of any "chance of profit"
  figure, never invented
- `proposals/` — builds a structured trade proposal (entry/stop/target/
  size + backtested stats) for human review; returns `None` if no valid
  setup exists rather than forcing one
- `db/` — PostgreSQL persistence layer (SQLAlchemy models + Alembic
  migrations): `assets`, `candles`, `backtest_runs`, `backtest_trades`,
  `signals`. Minimal by design — see `db/models.py`'s module docstring
  for what's deliberately not built yet (orders, positions, portfolios,
  etc.) and why.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Local Postgres (see docker-compose.yml — host port 5433, not 5432)
docker compose up -d
alembic upgrade head

python main.py
```

No API keys are required to run Phase 1 (historical kline data is public).
If you later add live-account features, set these as environment
variables — never hardcode them:

```bash
export BYBIT_API_KEY=...
export BYBIT_API_SECRET=...
export BYBIT_TESTNET=true
```

## Configuration

All risk, pair, and strategy parameters live in `config/config.py` — that
is the single place to adjust account size, risk-per-trade %, pairs,
timeframes, and indicator periods.

## Roadmap

See `docs/ARCHITECTURE.md` for the full Phase 1-4 plan: strategy modules
+ human approval loop (Phase 2), on-chain/macro context layers (Phase 3),
testnet validation and small live capital with an evolving multi-agent
synthesis layer (Phase 4).

## Explicitly out of scope right now

- Intraday/scalping timeframes
- High leverage (capped at 1x to start)
- Unattended live execution
- Any guaranteed or fixed-timeline return target
