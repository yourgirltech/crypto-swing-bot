# Master Plan — AI-Powered Crypto Trading System

This is the master vision doc. `ARCHITECTURE.md` describes what's actually
built so far (Phase 1 backend core); this document is the full system this
project is growing into, and how the phases map onto it.

## Relationship to current repo

Everything in `docs/ARCHITECTURE.md` (market structure engine, indicators,
regime classifier, backtest engine, trade proposal builder) is the
**Market Analysis Engine + Backtesting Engine + part of the Risk
Management Engine** in the pipeline below. Nothing already built conflicts
with this fuller plan — it slots in as the analysis core. What's new here:
a persistence layer (Postgres), a frontend dashboard, a formal risk-engine
authority model, ML as a ranking/classification tool (not a predictor),
and a concrete capital-scaling path.

**Capital plan (supersedes the old ₦1,000,000-generic framing):**
- Total available capital: ₦1,000,000.
- Initial live trading test: **₦100,000** only.
- Remaining ₦900,000 stays outside the system entirely until the system
  earns the right to manage more, based on defined scaling criteria (see
  §15), not simply because it made money.

---

## 1. System Architecture

```
Crypto Exchange(s) [Bybit primary]
        ↓
Market Data Engine        (REST historical + WebSocket real-time)
        ↓
Data Processing           (cleaning, resampling, storage)
        ↓
Market Analysis Engine     (structure, indicators — ALREADY BUILT, Phase 1)
        ↓
Market Regime Detection    (ALREADY BUILT, Phase 1)
        ↓
Strategy Engine            (modular strategies, regime-gated — Phase 2)
        ↓
AI / ML Layer              (regime classification, signal ranking,
                            anomaly detection, LLM synthesis — Phase 2-4)
        ↓
Risk Management Engine     (has VETO authority over every layer above it)
        ↓
Portfolio Management       (position/exposure tracking across the account)
        ↓
Trade Execution Engine     (paper → testnet → live, human-approved)
        ↓
Monitoring & Kill Switch   (circuit breakers, system health)
        ↓
Analytics Dashboard        (Next.js frontend)
```

The risk engine sits directly above execution and has override authority
over the strategy engine and AI layer — a high-scoring signal that fails a
risk check must never reach execution. This mirrors the existing
`config/config.py` design (risk % and position caps as separate, protected
config) but formalizes the risk engine as an active gate, not just config.

## 2. Technology Stack

**Frontend:** Next.js, React, TypeScript, Tailwind CSS, Recharts.
**Backend / trading engine:** Python, FastAPI, Pandas, NumPy, SciPy,
scikit-learn (regime classification, signal ranking), PyTorch only if/when
a specific model justifies it — not by default. SQLAlchemy as the ORM.
**Database:** PostgreSQL.
**Infrastructure:** Docker for local + deployment consistency. Redis/Celery
only introduced when a genuine async need appears (e.g. background
backtests, scheduled data pulls) — not upfront.

This matches your existing stack strengths (React/TypeScript from your
frontend work, Python/FastAPI from Clyra) rather than introducing new
unfamiliar tools where avoidable.

## 3. Project Folder Structure (monorepo)

```
crypto-trading-system/
├── backend/
│   ├── data/            # exchange clients, WebSocket + REST ingestion
│   ├── structure/        # market structure engine (from Phase 1 repo)
│   ├── indicators/       # technical indicators (from Phase 1 repo)
│   ├── regime/           # regime classifier (from Phase 1 repo)
│   ├── strategies/       # strategy modules (Phase 2+)
│   ├── ml/               # regime classification models, signal ranking, anomaly detection
│   ├── risk/             # risk engine — position sizing, exposure limits, kill switch
│   ├── portfolio/        # position/portfolio state management
│   ├── execution/        # paper / testnet / live execution engines
│   ├── backtest/         # backtesting engine (from Phase 1 repo)
│   ├── api/               # FastAPI routes serving the frontend
│   ├── db/               # SQLAlchemy models + migrations
│   ├── config/            # risk %, pairs, timeframes, environment flags
│   ├── tests/
│   └── journal/           # trading journal logging
├── frontend/
│   ├── app/               # Next.js app router pages (dashboard, markets,
│   │                       #  signals, positions, orders, strategies,
│   │                       #  backtesting, ai-insights, risk, journal, system-health)
│   ├── components/
│   └── lib/                # API client, chart helpers
├── docker-compose.yml
└── docs/
    ├── ARCHITECTURE.md      # Phase 1 implementation detail (existing)
    └── MASTER_PLAN.md       # this file
```

## 4. Development Roadmap — Milestones

Each milestone lists what's built, the Python concepts needed, and the
trading knowledge needed, so you can sequence learning alongside building
rather than needing to know everything upfront.

**Milestone 0 (DONE):** Python trading environment, Bybit historical data
client, market structure engine, indicators, regime classifier, backtest
engine, trade proposal builder. *(This is the current repo.)*
— Python needed: pandas/numpy fundamentals, dataclasses, basic OOP.
— Trading knowledge needed: candlesticks, swing highs/lows, trend
  structure, basic indicators (EMA/RSI/ATR).

**Milestone 1 (DONE, 2026-08-25):** PostgreSQL persistence layer via
SQLAlchemy + Alembic, Docker Compose for local Postgres. Built minimal —
only `assets`, `candles`, `backtest_runs`, `backtest_trades`, `signals`
(no `orders`/`positions`/`portfolios` yet — no engine produces that data
yet; see `db/models.py`'s docstring). `main.py` now persists every run.
— Python: SQLAlchemy ORM basics, Alembic migrations.
— Trading: none new — this is plumbing.

**Milestone 2:** Risk Management Engine as an active gate (not just
config) — position sizing calculator, max exposure/correlation checks,
daily/weekly loss circuit breakers, kill switch conditions (§11-12).
— Python: state machines, simple rule engines.
— Trading: position sizing math, correlation between BTC/ETH exposure,
  drawdown vs. max-loss distinction.

**Milestone 3:** First strategy module (trend-continuation, formalized
from the current backtest logic) with explicit entry/confirmation/
invalidation/stop/target/exit conditions, gated by regime.
— Python: strategy interface/abstract base class pattern.
— Trading: why trend-following works when it works (persistence of
  momentum) and fails (trend exhaustion, chop).

**Milestone 4:** Paper trading engine — simulates fills, fees, slippage
against live price feed, logs every simulated trade to the journal table.
— Python: async/WebSocket handling (real-time price feed).
— Trading: realistic execution assumptions (slippage, spread) vs. naive
  backtest assumptions.

**Milestone 5:** Trading journal + FastAPI endpoints exposing it.
— Python: FastAPI routing basics.
— Trading: none new — recordkeeping discipline.

**Milestone 6:** Frontend dashboard (Next.js) — Dashboard, Positions,
Orders, Strategies, Backtesting pages first; AI Insights/Risk/Journal/
System Health pages after.
— Python: none (frontend work, matches your existing React/TS skill).
— Trading: understanding what numbers matter enough to surface (win
  rate, expectancy, drawdown, exposure) vs. vanity metrics.

**Milestone 7 (DONE, 2026-08-26):** Additional strategy modules
(breakout, pullback, mean-reversion, range) — each independently
backtested, none assumed profitable until proven. **Actual outcome: one
validated strategy total (TrendContinuationBOS, from Milestone 3),
four new ones honestly tested and shelved, not forced into service.**
Breakout overfit (in-sample edge inverted held-out); Pullback showed no
edge in-sample or held-out; Mean-reversion showed no edge even after a
second backtest specifically isolating and removing a real exit-logic
confound (fixed reward:risk target mismatched to its trade shape); Range
trading came closest (held-out expectancy near break-even) but still
didn't clear the validation bar. None are registered in
`strategies/registry.py` or exposed on the frontend Strategies page — see
docs/ARCHITECTURE.md's "Milestone 7 close-out" section for full
per-strategy numbers and reasoning. Real, reusable infrastructure now
exists for future strategy research regardless of this milestone's
specific results: `db.repository.get_candles()` (backtest off persisted
history, no live exchange dependency), `backtest/validate_milestone7.py`
(a full/in-sample/held-out validation runner, not a one-off script), and
a `Strategy.compute_take_profit()`/`check_exit()` interface that supports
a genuine per-strategy exit rather than one fixed target borrowed from
the first strategy ever built.
— Trading: when each strategy style works/fails, tied to regime — in
  this case, four candidates were tested and none held up, which is
  itself a real trading-knowledge result (BTC 4H apparently rewards this
  project's specific trend-continuation definition more than these four
  breakout/pullback/reversion/range definitions did), not a null result.

**Milestone 8 (DEFERRED, 2026-08-26 — not done, not silently skipped):**
Market regime detection formalized as an ML classification task
(features: trend slope, ATR ratio, drawdown/rally magnitude — already
computed in Phase 1 — fed into a simple classifier instead of hardcoded
thresholds). **Checked against real evidence before writing any model
code, per this project's no-black-box-without-cause standard: does
Milestone 7's evidence show the rule-based classifier actually causing
strategy failures a better classifier would fix?** Checked
Mean-reversion (unambiguous — 100% of its trades are, by its own gate,
in the one regime it targets, and it still failed twice), and the real
held-out regime breakdowns for Breakout and Range trading (the two
strategies with any full-period regime-related pattern at all). **None
showed evidence that regime mislabeling caused a failure a better
classifier would have prevented** — see docs/ARCHITECTURE.md's
"Milestone 8 — DEFERRED" section for the full per-strategy breakdown.
Building an ML classifier without that evidence would likely just
re-derive similar thresholds with more parameters and less
explainability — a regression against this project's own "every label
traceable to the numbers behind it" principle, not progress. Deferred
until there's an actual case for it. **The one legitimate future
direction if revisited**: supervised training directly on raw features
vs. REAL trade outcomes (realized R-multiples), not on "what would the
existing rule-based function have said" — the latter can only ever match
or underperform the rules it imitates and adds complexity without adding
signal.
— Python: scikit-learn basics (train/test split, classification metrics)
— not yet needed, since the milestone itself is deferred.
— Trading: avoiding overfitting a regime label to one historical period
  — and, as it turned out, avoiding building a solution before confirming
  there's a real problem it solves.

**Milestone 9 (DEFERRED, 2026-08-26 — not done, not silently skipped):**
Derivatives data (funding rate, open interest, long/short skew) as
contextual filters, not signals. **Checked for evidence before wiring
anything into the live trading path, same standard as Milestone 8:** no
existing evidence (nothing tracked before), and — confirmed by directly
hitting OKX's live API, not assumed — the obvious retroactive test
(align funding/OI/long-short history against the 126 already-persisted
`TrendContinuationBOS` trades) is structurally impossible: all three OKX
endpoints cap out at ~3 months of public history (earliest reached:
2026-05-19/25), against a nearly 5-year trade history. See
docs/ARCHITECTURE.md's "Milestone 9 — DEFERRED" section for the exact
endpoints/dates checked. **Built instead: passive collection only** — a
new `derivatives_snapshots` table plus three new `OKXClient` methods,
called once per `paper_trading/engine.py` poll cycle, verified with a
real poll/save cycle (real values persisted, failure-isolation boundary
confirmed with a bogus symbol). Not read by any strategy, risk engine, or
dashboard page — purely to start accumulating real, aligned data now, so
a genuine evidence-based test is possible after enough paper-trading
history exists, rather than staying permanently untestable.
— Trading: what funding rate extremes and OI buildup actually indicate
  — and, same lesson as Milestone 8, not assuming a feature belongs in
  the system before there's a real case for it, even when the case can't
  be checked instantly and requires patiently collecting evidence first.

**Milestone 10 (PREREQUISITE MET AND LIVE IN PAPER TRADING, 2026-08-27):**
Market scanner ranking multiple assets by signal quality — still gated by
strategy → risk → portfolio validation before anything becomes a
proposal. Previously assessed as having no real prerequisite (one active
asset, nothing to rank); that changed when Breakout was found to
genuinely held-out validate on ETHUSDT (held-out: 22 trades, +0.091R,
sign held from in-sample) — a real, evidenced second asset/strategy pair,
independent of `TrendContinuationBOS`'s BTC validation.

Before treating that as a go-live decision rather than just "validated,"
three things were checked with real data, not assumed:
1. Built `backtest/combined_portfolio_backtest.py` — every prior backtest
   tracked only one open position at a time; this runs both strategies as
   ONE real portfolio (shared balance, concurrent positions) across their
   aligned 5yr history. Found 49 genuine concurrent entries; uncapped,
   combined notional naturally reached up to 141% of equity — confirming
   `max_leverage=1.0` alone (a per-trade check) would NOT have caught a
   real over-100%-of-equity combined exposure scenario.
2. Re-derived `max_portfolio_exposure_pct`/`max_correlated_exposure_pct`
   85% → 90% using that real data (natural cluster ceiling ~88.90%, then
   a jump to 107.61%/141.45%, nothing in between) — same "find the gap"
   methodology as `max_position_size_pct`'s own Milestone 4 derivation.
   Re-verified both single-asset results stayed byte-identical after the
   change (the cap only affects concurrent sizing).
3. Built the real per-symbol-strategy mapping (`strategies/registry.py`'s
   `STRATEGY_FOR_SYMBOL`) that `paper_trading/engine.py` and `main.py`
   both import — replacing the old hardcoded single-strategy assumption
   in both files.

**Now live**: `MARKET.pairs` is `["BTCUSDT", "ETHUSDT"]`, each running its
own assigned strategy (`TrendContinuationBOS` for BTC, `Breakout` for
ETH). `strategies/registry.py` and the frontend Strategies page correctly
show both with their own real, distinct backtested stats (verified via
screenshot — no shared/duplicated numbers). The paper trading engine was
restarted and its first poll cycle confirmed evaluating both symbols
independently, each against its own strategy, with real OKX data.

Since this is paper trading — no real capital at stake — **this
activation itself IS the real-world validation period Milestone 10
needs, not a separate step still owed.** Any live-trading discussion for
ETH/Breakout is a distinct, later decision, gated on how this paper
period actually performs.
— Python: batch processing across symbols efficiently.

**Milestone 11:** On-chain + macro context layers (Phase 3 from the
existing architecture doc) as slow-moving bias filters.

**Milestone 12:** Testnet execution validation, then live trading with
₦100,000, monitored against the scaling criteria in §15.

## 5. Recommended Initial Exchange/API Architecture

Start with Bybit only (already the documented exchange). REST for
historical backfill, WebSocket for real-time candles/order book once
paper trading begins. Wrap the exchange client behind an interface
(`ExchangeClient` abstract base) from the start, even with only one
exchange implemented — this is what "add more exchanges later" in your
spec actually requires structurally, and it costs little to do now vs.
retrofitting later.

## 6. Database Architecture (high-level)

Core tables: `assets`, `candles` (timeframe-partitioned), `signals`,
`strategies`, `orders`, `positions`, `portfolios`, `executions`,
`performance_metrics`, `model_predictions`, `trading_decisions`,
`system_events`, `errors`. Candles table should be indexed on
(asset_id, timeframe, open_time) as the primary access pattern. Detailed
schema to be written at Milestone 1, once the exact fields each engine
needs are settled — designing the full schema before any engine consumes
it risks guessing wrong.

## 7. Backtesting Architecture

Already implemented (walk-forward, no look-ahead — see
`backtest/backtest_engine.py`). To extend toward the fuller spec:
add fee/slippage modeling (config already has placeholders in
`BACKTEST` config), profit factor, Sharpe/Sortino ratios, and out-of-
sample / walk-forward validation (train on one period, validate on an
unseen later period) before any strategy is considered validated.

## 8. Risk Management Architecture

Formal authority model: the risk engine evaluates every proposal from
the strategy engine and can REJECT with a stated reason (matches your
spec's `Risk Engine: REJECT / Reason: ...` example) before it ever
reaches execution. Enforces: max risk per trade, max position size, max
portfolio exposure, max daily/weekly loss (circuit breaker), max
drawdown, max open positions, max correlated exposure (BTC+ETH count as
correlated, not independent), max leverage, mandatory stop-loss,
emergency shutdown conditions.

## 9. AI/ML Architecture

ML is used for: regime classification (Milestone 8), signal ranking
across scanned assets (Milestone 10), anomaly detection (unusual volume/
volatility/funding — flagged as caution signals, not trade triggers), and
feature analysis (which variables correlate with historically successful
setups, used to refine strategy conditions, not to invent new ones
blindly). An LLM may narrate/summarize (matches the existing "LLM
synthesis layer" in ARCHITECTURE.md) but never issues a trade decision
directly — every AI output passes through strategy validation and risk
validation, exactly as your spec requires.

## 10. Testing Strategy

Unit tests for all deterministic logic (structure detection, indicators,
position sizing, risk checks) — these must be correct 100% of the time,
so they're the highest testing priority. Integration tests for the
backtest engine against known synthetic scenarios (e.g. a manufactured
uptrend should produce an expected number of long signals). Paper
trading itself serves as the system-level test before testnet/live.

## 11. Security Architecture

API keys via environment variables only, never committed, never in
frontend code (already reflected in `.gitignore` and `config.py`).
Exchange API keys scoped to trading permissions only — no withdrawal
permission, ever. Secrets management via `.env` for now; consider a
proper secrets manager (e.g. Docker secrets) before live capital is at
stake.

## 12. Deployment Strategy

Local Docker Compose for development (Postgres + backend + frontend).
Defer cloud deployment decisions until paper trading is stable — no
reason to pay for infra before the system proves anything. When ready,
containerized deployment (backend API + scheduled data jobs + frontend)
on any Docker-friendly host.

## 13. Capital Scaling Path

Starting point: ₦100,000 live, ₦900,000 held outside the system.
Scale-up is **never** automatic on profit alone. Before increasing
allocation, require:
- A meaningful number of live trades (not backtest trades) — think
  several dozen at minimum, not 3-5.
- Live performance statistically consistent with backtested expectancy
  (if backtest expectancy was +0.3R and live is wildly different, that's
  a signal to investigate, not scale).
- Max drawdown observed live stays within the pre-defined risk limits.
- Performance holds across more than one market regime (a system that
  only works in a trending bull market hasn't been tested by a range or
  a bear leg yet).
- No unexplained strategy behavior changes (silent overfitting drift).

Only once these hold up should capital allocation increase, and even
then, incrementally (e.g. ₦100k → ₦200k), not all-at-once.

---

## What changes in the existing repo right now

Nothing needs to be torn down. The current `crypto-swing-bot` repo becomes
`backend/` in the eventual monorepo, and `ARCHITECTURE.md` stays accurate
as the Phase 1 implementation record. This file is the map for everything
after Milestone 0.
