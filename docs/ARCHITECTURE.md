# Crypto Swing Trading Bot — Architecture & Plan

> This document covers the Phase 1 backend core, already implemented.
> For the full system vision (frontend dashboard, database, ML layer,
> risk engine authority model, capital scaling plan), see
> [`MASTER_PLAN.md`](MASTER_PLAN.md) — read both.

## Goal
Preserve capital, grow steadily. This is NOT a "double your money fast" bot.
Total available capital: ₦1,000,000, but only ₦100,000 is earmarked for the
initial live trading test once Phase 1-4 validation is complete — the
remaining ₦900,000 stays outside the system entirely until it earns the
right to manage more (see `MASTER_PLAN.md` §15 for scaling criteria).
Target: realistic steady growth (think 15-40% over a few months in a
favorable environment), not a fixed timeline return.
No leverage or very low leverage (1x, maybe 2x once proven). Small risk per
trade (0.5-1% of account). Human approves every trade before execution —
the bot never trades unattended in early phases.

## Style
- **Swing trading**: multi-day holds, not scalping/intraday.
- **Primary timeframes**: Daily (trend/structure context) + 4H (entry timing).
- **Starting pairs**: BTC/USDT and ETH/USDT were the original pair set
  (most liquid, cleanest structure, lowest manipulation risk vs.
  altcoins). **As of 2026-08-24, active trading focus is BTC/USDT only —
  ETH/USDT is paused, not removed.** A 5-year walk-forward backtest of
  the trend-continuation BOS setup showed ETH net-unprofitable
  (-0.065R expectancy over 138 trades) with losses spread across
  regimes rather than concentrated in one (sideways: -0.385R,
  strong_bear_trend: -0.400R) — that pattern indicates the entry logic
  itself doesn't suit ETH's price behavior, not a regime-gating problem
  a filter could fix. `data/okx_client.py` and the rest of the pipeline
  still support ETH so it can be revisited with different strategy
  logic later (see `config/config.py` `MARKET.pairs` comment). Expand
  pairs again once the system proves itself further.
- **Exchange**: Bybit (spot first; futures/perps only once strategy is
  validated and only with capped low leverage).
- **Network access from this dev machine**: Bybit's public API returns
  HTTP 403 (CloudFront geo-block) and Binance returns HTTP 451 from this
  machine/network — neither is reachable directly, which is why
  `data/okx_client.py` exists as a same-interface drop-in substitute for
  BACKTESTING purposes only (Bybit remains the documented execution
  exchange; see `main.py`'s module docstring). **Update, 2026-08-26: OKX
  itself also became unreachable from this network** (`www.okx.com` failed
  DNS resolution — `getaddrinfo failed` — while unrelated hosts like
  `google.com` resolved fine, confirming it's an OKX-specific block, not a
  general outage) — the same ISP-level blocking pattern as Bybit/Binance,
  just arriving later. **A VPN is now required to run this project at all
  from this network** (confirmed: enabling one made `www.okx.com` resolve
  correctly again). If a future session sees `ConnectionError`/DNS
  failures on OKX calls, check the VPN before re-diagnosing this as a new
  problem — it almost certainly isn't one.

## Strategy refinement: weak_bull_trend EMA21 confirmation filter

As of 2026-08-25, the trend-continuation BOS entry applies one extra
confirmation condition when the regime is `weak_bull_trend`: price must
actually be trading above the fast EMA (21), not just satisfy the
existing EMA21>EMA50 cross (`trend_filter="bullish"`). Originally
implemented as a standalone `backtest_engine.weak_bull_trend_ema_filter`
function passed into `run_backtest()` as an `entry_filter` callable, and
duplicated by hand inside `proposals/trade_proposal.py`'s `build_proposal`
to keep the two in sync.

**Superseded by Milestone 3** (see "Strategy interface" section below):
this filter now lives as `TrendContinuationBOS.confirm_entry()` in
`strategies/trend_continuation_bos.py` — part of the strategy itself, not
a bolt-on parameter — and both `run_backtest()` and `build_proposal()`
call the SAME strategy instance, so there's no more hand-kept-in-sync
duplication. The logic and validation history below are unchanged, only
where the code lives changed.

**Why:** `weak_bull_trend` was BTC's most common regime (78/149 trades
over 5yr) and the one dragging overall expectancy negative (-0.038R).
Within it, winning trades entered with price meaningfully above EMA21
(+0.47% avg) while losing trades entered at/below it (-0.11% avg).

**Validation status — held-out tested, not fully proven:** an out-of-
sample check (first 4yr as training, most recent 1yr as held-out, not
used to pick the filter) confirmed the filter helps directionally in
every slice checked (win rate and expectancy both improve, training and
held-out, regime-specific and overall) — but more modestly than the
full-period number implied. On held-out data alone, `weak_bull_trend`
stayed net-negative even with the filter (-0.143R -> -0.100R, 14->10
trades) rather than flipping to profitable as it did on the training-
heavy full-period number (+0.091R). **The filter reduces the damage in
this regime; it does not cure it.** Held-out sample sizes are small
(10-14 trades), so treat this as a live lead worth further iteration,
not a finished, fully-proven fix.

## Risk Management Engine (Milestone 2)

`risk/risk_engine.py`'s `evaluate_trade(proposal, portfolio, risk_config)`
is an active APPROVE/REJECT gate, not just config values sitting unread.
`main.py` and `proposals/trade_proposal.py`'s call site run every
`TradeProposal` through it before `db.repository.save_signal()` persists
it — `signals.status` is set to `approved`/`rejected` directly from the
verdict, and the new `signals.risk_verdict_reason` column records *why*
on a rejection.

Rules are checked in a fixed order: account-wide circuit breakers first
(max drawdown, daily loss, weekly loss — independent of the specific
proposal, and any one of them blocks everything), then a mandatory-stop-
loss sanity check, then per-trade sizing (leverage, risk-per-trade,
position size), then portfolio-wide checks (open positions count, total
exposure, correlated exposure). First failing rule short-circuits with a
specific reason; `RiskVerdict.checks` carries every rule's pass/fail for
audit.

New `RiskConfig` values added 2026-08-25 (confirmed with user rather than
picked silently): `max_position_size_pct=20`, `max_portfolio_exposure_pct
=50`, `max_drawdown_pct=15` (deliberately above BTC's backtested max DD
of -11.57%, as a live-variance buffer), `max_correlated_exposure_pct=30`
with `correlated_groups=[["BTCUSDT","ETHUSDT"]]`.

**Known limitation:** there is no orders/positions table yet (deferred to
Milestone 4's paper trading engine, which is what will actually produce
fills). `main.py` currently evaluates every proposal against an empty/
at-rest `PortfolioState` (no open positions, zero daily/weekly P&L, no
drawdown) rather than inventing numbers with no real data behind them —
consistent with this project's rule that a "chance of profit" or exposure
figure is never guessed. The per-trade checks (leverage, risk-per-trade,
position size, mandatory stop-loss) are fully real and enforced today;
the portfolio-wide checks (open positions, total/correlated exposure)
are correct but have nothing to bite on until Milestone 4 exists to feed
them real state. Same reasoning applies to `correlated_groups` only ever
containing BTC while ETH stays paused.

## Strategy interface (Milestone 3)

`strategies/base.py`'s `Strategy` ABC formalizes what was, until
2026-08-25, trend-continuation BOS logic written directly inside
`backtest_engine.run_backtest()` and separately (hand-kept-in-sync)
inside `proposals/trade_proposal.py`'s `build_proposal()`. Both call
sites now take a `Strategy` instance and delegate every decision to it —
`check_entry`, `confirm_entry`, `check_invalidation`, `compute_stop_loss`,
`compute_take_profit`, `position_size`, `check_exit`, and
`market_regime_requirements`. Neither `run_backtest()` nor
`build_proposal()` knows which concrete strategy it's running; both own
only the shared mechanics (structure/regime engines, walk-forward window
management, persistence).

`strategies/trend_continuation_bos.py`'s `TrendContinuationBOS` is the
first (and, for now, only) concrete strategy — it's the exact same rules
that existed before this refactor: BOS + EMA cross + RSI-not-extreme
entry, ATR-multiple stop, fixed-R:R target, fixed-fractional position
sizing, stop/target-hit exit, and the `weak_bull_trend` EMA21
confirmation filter (see "Strategy refinement" above) as
`confirm_entry()`. `check_invalidation()` always returns `False` today —
this strategy has no pending, multi-bar setup window to invalidate before
a fill triggers; the method exists on the interface for a strategy that
does need one (a future variant, or a Milestone 7 addition) to actually
use.

`main.py` and `build_proposal()` both construct one `TrendContinuationBOS()`
and pass it to `run_backtest()` / `build_proposal()` respectively — this
is also what removes the drift risk the pre-refactor code called out in
its own comments ("kept consistent so these don't drift").

## Paper trading engine (Milestone 4)

`paper_trading/engine.py` is a standing, manually-run loop — not a one-
shot script like `main.py`. Each poll cycle either monitors an already-
open paper position for a stop/target hit, or scans for a new entry.

**Design decision (confirmed with the user 2026-08-25): paper trades
require EXPLICIT HUMAN APPROVAL, exactly like live trading will — there
is no auto-execute mode.** The goal is to build the actual human-approval
habit and workflow now, not just simulate fills faster. A risk-engine-
APPROVED proposal is shown as a full plain-language review
(`reporting.plain_language_summary.explain_full_trade_review` — setup and
why it triggered, backtested track record with a small-sample caveat, a
plain-language win/loss estimate grounded only in that backtested history,
entry/stop/target/R:R with the ATR reasoning, position size and the
actual ₦ risked, current risk-engine budget usage, and caveats about data
source and paper-vs-live) and the loop blocks on a real y/n before doing
anything. A risk-engine-REJECTED proposal is logged with its reason and
never even shown to a human — there is nothing to approve.

**Price feed decision (confirmed with the user 2026-08-25): REST POLLING
ONLY, not WebSocket**, despite MASTER_PLAN.md naming async/WebSocket
handling as this milestone's Python-skill goal. Entries only ever trigger
on a CLOSED 4H candle anyway (`strategy.check_entry`), so real-time ticks
add nothing there; checking stop/target against the same closed-candle
high/low the backtest was validated against (`strategy.check_exit`) keeps
paper trading a fair like-for-like test of what was actually backtested,
rather than testing a finer-grained behavior that was never validated.
The cost — up to ~4h of delay finding out a stop/target was hit — has
zero real consequence in paper trading, since no real capital is exposed
during that delay. OKX's WebSocket endpoint (`ws.okx.com:8443`) was
confirmed reachable (TLS handshake succeeds) from this dev machine, so
this was a deliberate simplicity choice, not a connectivity fallback.
**Revisit at the live-trading milestone (Milestone 12)**, where a real-
time reaction actually reduces real risk.

**New tables:** `paper_trades` (its own table, not reused from
`backtest_trades` — exactly the "different fields: fills, fees, order
refs" case anticipated when `backtest_trades` was named to avoid this
future clash). `signals` gained `triggering_candle_time` (which candle's
close produced this signal, so the engine can tell "already decided for
this candle" apart from "a genuinely new candle closed", across polls
*and restarts*) and a separate `human_decision`/`human_decision_reason`/
`human_decision_at` — orthogonal to `status` (the risk engine's verdict,
Milestone 2), since a human is never even asked about a REJECTED signal.

**Realistic vs. naive execution:** `paper_trades` simulates fills using
`config.BACKTEST.slippage_pct`/`fee_pct` (reused, not reinvented) on both
legs, and stores BOTH `r_multiple_ideal` (the backtest's naive -1.0/
+reward_risk) and `r_multiple_realistic` (after slippage+fees) — the gap
between the two is exactly the "realistic execution assumptions vs naive
backtest assumptions" comparison MASTER_PLAN.md names for this milestone.

**Resolves a Milestone 2 known limitation:** `db.repository.
build_portfolio_state()` now builds a REAL `PortfolioState` from actual
`paper_trades` rows (open positions, realized P&L since the account
baseline, running peak equity for drawdown) — `main.py`'s demo path and
`paper_trading/engine.py` both use it now instead of an empty/at-rest
stub. It legitimately comes back empty until the first paper trade
closes; that's real absence of history, not a stand-in for missing data.

**Real bug caught while building this:** `save_signal()` (and the new
`create_paper_trade()`/`close_paper_trade()`) needed the same
`numpy.float64` → native `float` coercion `_f()` already used in
`save_backtest_trades` (Milestone 1) — `save_signal()` had never actually
been exercised with a non-None proposal until this milestone's end-to-end
test, so this bug existed silently since Milestone 2.

**Real finding surfaced by testing, and now RESOLVED (2026-08-25):** given
`risk_per_trade_pct=1%` and this strategy's typical ATR-based stop
distance (~2% of price), position sizing naturally computes to ~46% of
equity notional (median across all 126 backtested trades) — 96% of those
126 trades would have been REJECTED by the original `max_position_size_pct
=20%` alone. Rather than loosen the cap to accommodate every trade at full
risk (the user's rejected first proposal), the actual fix was to change
position sizing itself.

## Multi-constraint position sizing (Milestone 4 calibration fix)

`risk/position_sizing.py`'s `size_position()` computes the ACTUAL position
size as `min(risk-based size, tightest of three notional caps)` — a trade
whose risk-based size would exceed any of `max_position_size_pct`/
`max_portfolio_exposure_pct`/`max_correlated_exposure_pct` sizes DOWN and
risks LESS than `risk_per_trade_pct` on that one trade, rather than being
blocked outright or forcing a cap to be loosened for everyone. Called from
both `backtest_engine.run_backtest()` (now takes `risk_config: RiskConfig`
+ `symbol`, replacing separate `risk_per_trade_pct`/`max_position_size_pct`
floats) and `proposals/trade_proposal.py`'s `build_proposal()` (now takes
`risk_config` + `portfolio: PortfolioState`, replacing `account_balance`/
`risk_per_trade_pct`/`max_position_size_pct`) — the same one-shared-
implementation principle Milestone 3 established for entry/stop/target
logic, now applied to sizing. `OpenPosition`/`PortfolioState` live in
`risk/position_sizing.py` (not `risk/risk_engine.py`, which re-exports them)
specifically to avoid a circular import with `trade_proposal.py`.
`backtest_engine.Trade` gained `position_size`/`risk_amount` (actual,
post-cap)/`was_capped`/`binding_constraint` fields; `BacktestResult.
sizing_summary()` reports how many trades were capped and by which
constraint. `risk_engine.evaluate_trade()`'s own position/portfolio/
correlated checks are now genuine backstops/defense-in-depth — sizing
already guarantees compliance before a proposal reaches them.

**Extended mid-fix to all three caps, not just position size:** the first
pass fixed only `max_position_size_pct`. Re-running the 126-trade backtest
with real numbers immediately showed the identical miscalibration in
`max_portfolio_exposure_pct` (50%) and `max_correlated_exposure_pct` (30%)
— with BTC-only trading and `max_open_positions` never actually reaching 2
concurrent positions in practice, "portfolio exposure" and "correlated
exposure" collapse to exactly the same number `max_position_size_pct`
already measures (a lone position's own notional). At the old 50%/30%,
84.1% of trades were still capped by `correlated_cap` alone, dragging mean
effective risk back down to 0.689% — nearly undoing the position-size fix.
All three are now 85% for the SAME data-driven reason, confirmed via full
re-run (see `config/config.py`'s `RiskConfig` comment, marked prominently):
**this is a temporary coincidence of BTC-only/single-position trading, not
a permanent design decision** — the moment ETH resumes (making 2 real
concurrent positions possible), `max_correlated_exposure_pct` (and, once
`max_open_positions` can actually be reached, `max_portfolio_exposure_pct`)
must be independently re-derived against real two-asset combined-exposure
data, not assumed to still fit.

**Verified empirically, not just reasoned about:** re-ran the full
126-trade BTC backtest at several candidate cap values. `win_rate_pct`/
`avg_win_r`/`avg_loss_r`/`expectancy_r` were IDENTICAL at every cap tested
(37.3% / 2.0 / -1.0 / +0.119R) — these are R-multiple stats, position-
size-independent by construction, so capping a trade's size can never
change them; only `max_drawdown_pct` and the equity curve's path move
(non-monotonically with tighter caps — a real compounding-path effect).
Confirmed every capped trade's effective risk stayed `> 0%` and `<= 1.0%`,
never above target.

**The actual miscalibration was the cap being too LOW, not too high** —
counterintuitively. At 20%, 96% of trades got capped down to a MEAN
effective risk of ~0.46% (not 1%) — meaning 20% was the routine sizing
mechanism, not a rare backstop, silently running the whole strategy at
roughly half its intended risk-per-trade. `max_position_size_pct` is now
**85%** (up from 20%, confirmed with user 2026-08-25) — the real gap in
the data: every one of the 126 trades' true (uncapped) notional size
tops out at 79.38%, then jumps straight to 102.48%+ (already independently
rejected by `max_leverage=1.0`) — nothing in between. With all three caps
at 85% (final live config), confirmed via full re-run: only 5/126 trades
(4.0%, all pre-existing max_leverage outliers) ever hit any cap, all via
`position_cap`; mean effective risk across all 126 trades is 0.989%
(median exactly 1.000%) — essentially the full intended target, exactly
what a genuine backstop should look like.

**Is `risk_per_trade_pct` itself part of the issue?** Mathematically yes —
`position_size_pct = risk_per_trade_pct × (entry_price / stop_distance)`,
a pure linear multiplier — but it's the wrong lever for this problem.
`risk_per_trade_pct` answers "how much am I willing to lose on one trade"
(1% is an unremarkable, standard setting; backtested max drawdown of
-11.57% at 126 trades is nothing alarming). `max_position_size_pct`
answers a different question — "how large a position am I willing to
hold, regardless of why" — a backstop against concentration risk or a
sizing bug. Fixing the backstop's own miscalibration with the backstop's
own parameter (via dual-constraint sizing) is the surgical fix; cutting
real risk-taking by more than half (`risk_per_trade_pct` would need to
drop to ~0.44% to get the MEDIAN trade under a 20% cap) just to patch a
cap-calibration problem would have been the wrong tool for the job.

## Trading journal + API (Milestone 5)

**The journal is deliberately NOT a new table.** Every trade's full
lifecycle — proposal, risk verdict, human decision, fill, exit, realized
P&L — is already captured across `signals` (Milestone 2/4) and
`paper_trades` (Milestone 4), linked 1:1 via `paper_trades.signal_id`.
`journal/service.py` is a QUERY layer composing the two into one
`JournalEntry` per signal; a new table would have created two sources of
truth for the same data, exactly the kind of duplication Milestone 3
removed for entry/stop/target logic and Milestone 4 removed for sizing.

A `JournalEntry` exists for EVERY signal, including risk-engine-REJECTED
and human-DECLINED ones — the `paper_trade_*` fields are simply `None` in
those cases. This is deliberate: the "why didn't we take this trade"
record is as much a part of the journal as executed trades are, matching
the project's transparency principle of never hiding the reasoning behind
a non-decision.

`api/main.py` is a FastAPI app (run via `uvicorn api.main:app --reload`)
exposing four read-only endpoints, all backed by `journal/service.py`:
- `GET /journal` — every signal ever generated, newest first, filterable
  by `symbol`/`risk_status`/`human_decision`/`outcome`.
- `GET /journal/{signal_id}` — one entry's full detail (404 if not found).
- `GET /journal/open` — currently open paper positions.
- `GET /journal/performance` — aggregate stats from CLOSED paper trades:
  win rate, `expectancy_r_ideal` (naive, backtest-style) AND
  `expectancy_r_realistic` (after simulated slippage+fees) side by side —
  the same "realistic vs. naive" comparison Milestone 4 introduced,
  now surfaced as a queryable metric rather than only visible per-trade.

`/journal/open` and `/journal/performance` are registered BEFORE
`/{signal_id}` in `api/routes/journal.py` — Starlette matches routes in
registration order, so the reverse order would make `/journal/open`
match `{signal_id}="open"` and fail int coercion (422) instead of hitting
the intended route.

CORS was added in Milestone 6 once the frontend actually existed (see
below), not on a guess beforehand.

**Verified against real data, not just unit-level:** started the actual
`uvicorn` server and hit every endpoint over real HTTP against the two
genuine signals already in Postgres from earlier `main.py` runs (one
risk-engine-approved, one rejected on correlated exposure), confirmed
filters/404/enum-validation all behave correctly, then ran a full
synthetic-but-real trade (real historical OHLCV, monkeypatched approval)
through open → close and confirmed `/journal/{id}` and `/journal/
performance` correctly reflected the populated fill/exit/P&L data over
HTTP — not just via direct Python calls to the service layer.

## Frontend dashboard (Milestone 6)

`frontend/` — Next.js 16 (App Router, Turbopack), TypeScript, Tailwind
CSS v4, React 19. Every page is a Server Component fetching directly from
the FastAPI backend (`frontend/src/lib/api.ts`, `cache: "no-store"` on
every request — this is live-ish trading data, a stale cache would be
actively misleading, not just a minor tradeoff). No mock data anywhere a
real endpoint exists.

**Design direction (confirmed with user 2026-08-26): dark terminal /
Bloomberg-terminal aesthetic.** Token system in `frontend/src/app/
globals.css` (Tailwind v4's CSS-first `@theme`, no `tailwind.config.js`):
`--color-base:#0a0e14`, `--color-surface:#12161d`, `--color-surface-hover:
#171c25`, `--color-border:#232a35`, `--color-primary:#e6e9ef`,
`--color-muted:#6b7280`, `--color-green:#22c55e`, `--color-red:#ef4444`,
`--color-amber:#f59e0b`. Typography: JetBrains Mono for all numbers/data
(tabular figures, self-hosted via `next/font/google`), IBM Plex Sans for
UI labels/nav — deliberately not Inter, the single most templated SaaS
default, per the `frontend-design` skill's guidance to avoid unexamined
defaults. Signature element: every risk-engine verdict / human decision
renders as a literal bracketed terminal stamp (`[ APPROVED ]` /
`[ REJECTED ]` / `[ DECLINED ]`, `components/VerdictStamp.tsx`) — ties the
visual identity to the actual mechanic this system is built around (the
risk engine's veto authority), not a decorative flourish. Hairline
dividers, sharp panels (0px radius, `.panel` class), no zebra striping,
no drop-shadow cards.

**Two small backend additions made to serve real data, not mocked
data, for pages that had no prior API:**
- `backtest/history.py` + `api/routes/backtests.py`: reads PERSISTED
  `backtest_runs`/`backtest_trades` (Milestone 1) for the Backtesting
  page. Honest limitation, not smoothed over: `max_drawdown_pct` isn't
  reconstructable from historical runs (position size/risk_amount were
  never persisted to `backtest_trades`, only added to the in-memory
  `Trade` dataclass in the Milestone 4 sizing fix) — omitted for
  historical runs rather than approximated from R-multiples alone, which
  would produce a number that doesn't match what the original run
  actually computed.
- `strategies/registry.py` + `api/routes/strategies.py`: no `strategies`
  DB table exists (deferred, see `db/models.py`'s Milestone 1 docstring)
  — describes the one real strategy (`TrendContinuationBOS`) from its
  actual instantiated parameters, not fabricated metadata; links to real
  backtested performance via the `/backtests` endpoint above.
- `api/routes/account.py`: the ticker bar needed "current equity," which
  wasn't exposed. Rather than hardcode the account baseline in the
  frontend, this reuses `db.repository.build_portfolio_state()`
  directly — the SAME function the risk engine itself uses — so there's
  one source of truth for account state, not a second computation of it.

**Real discovery while testing, not something to have guessed:** this
dev machine also runs a separate, unrelated project (Clyra) whose backend
already occupies port 8000. Found via a live port collision — `curl`
against port 8000 returned a completely different app's routes.
**This project's FastAPI now runs on port 8010** (`api/main.py`,
`frontend/.env.local`'s `API_BASE_URL`) rather than reclaiming 8000, so
both projects can run simultaneously without a conflict.

**Verified end-to-end against real data:** ran `tsc --noEmit` (clean),
started both servers (`uvicorn api.main:app --port 8010`, `npm run dev`
on 3000), and confirmed all 5 pages (`/`, `/positions`, `/orders`,
`/strategies`, `/backtesting`) return 200 with genuinely real backend
data (actual strategy parameters and backtested stats, actual signal
history, actual — empty, correctly — open positions). Also confirmed
visually via screenshot (the browser tool was initially flaky in this
environment — timed out/showed an error page on the first several tries,
then worked; see the charts section below) — dark theme, fonts, and
layout all render as designed.

## Charts (Recharts, added after initial review)

The first pass of Milestone 6 shipped numbers/tables/cards only — no
actual charts, despite MASTER_PLAN.md naming Recharts in the stack. Added
on request, real data only, one honest gap:

- **Equity curve** (`components/charts/EquityCurveChart.tsx`, Dashboard):
  fully dollar-accurate — unlike `backtest_trades`, `paper_trades` DOES
  persist real `pnl_ngn` per closed trade (Milestone 4), so
  `journal.service.get_equity_curve()` reconstructs a genuine ₦ curve, not
  an approximation. New `GET /journal/equity-curve`. Comes back as a
  single flat point at the account baseline until at least one real paper
  trade closes — shown honestly as an explanatory empty state, not a
  fabricated history.
- **Price action** (`components/charts/PriceChart.tsx`, Dashboard +
  Positions): real candlesticks from persisted `candles`, with EMA21/
  EMA50 recomputed via the actual `indicators.py` the strategy itself
  uses (not a lookalike), and entry/stop/target reference lines from a
  real signal/position. New `GET /market/candles`. Recharts has no native
  candlestick chart type — built one via a `Bar` whose `dataKey` is the
  `[low, high]` range (so Recharts' scale maps pixel y/height to that
  range) with a custom `shape` that derives the open/close body's pixel
  position from that same scale. Honest caveat shown in the UI: this is
  the **last-polled snapshot**, not a live feed — Milestone 4 deliberately
  chose REST polling over streaming, so there is no continuous real-time
  price stream in this system to show instead.
- **Backtest cumulative-R** (`components/charts/CumulativeRChart.tsx`,
  Backtesting): the one real gap. `backtest_trades` never persisted
  per-trade `position_size`/`risk_amount` (only added to the in-memory
  `Trade` dataclass during the Milestone 4 sizing fix, never to the DB
  schema) — so a dollar-accurate equity curve for historical runs can't
  be honestly reconstructed; approximating one from R-multiples alone
  (e.g. assuming equal sizing) would produce a number that doesn't match
  what the run actually computed. Built a **cumulative R-multiple**
  curve instead (`backtest.history.get_cumulative_r_curve()`, new
  `GET /backtests/{run_id}/cumulative-r`) — R-multiple is position-size-
  independent by construction, so this IS exact, just labeled honestly as
  R, not ₦. Verified against run #8: 126 points, ending at +15.0R
  (matches 126 × 0.119 expectancy).

**Verified with actual screenshots, not just HTTP 200s** — the browser
tool was flaky at first in this environment (timed out / showed an error
page on the first several attempts across two separate testing rounds),
but worked on retry both times; screenshots confirmed the dark theme,
real candlesticks with correctly-colored EMA lines and entry/stop/target
markers, and the full 126-trade cumulative-R curve rendering correctly
(a "vanishing after 3 points" look in one non-zoomed screenshot turned
out to be a JPEG compression artifact on a 1.5px line, not a real bug —
confirmed by zooming into the region directly).

## Second batch: AI Insights, Risk, Journal, System Health (Milestone 6)

Four more pages, same real-data-only rule, three small new read-only
endpoints:

- **Risk page** (`/risk`): `risk/status.py`'s `get_risk_status()` reuses
  `db.repository.build_portfolio_state()` directly (same function
  `evaluate_trade()` itself is fed) rather than recomputing account state
  a third time. New `GET /risk/status` returns the configured `RiskConfig`
  limits alongside CURRENT usage against each — a `BudgetBar` component
  (`components/BudgetBar.tsx`) visualizes "X% of Y% used," green/amber/red
  by proximity to the limit. The recent-verdicts log below it reuses the
  existing `GET /journal` — no duplicate data source for the same signals.
- **Journal page** (`/journal`): full filterable browse over `GET
  /journal`'s existing filters (Milestone 5) — implemented as a plain
  `<form method="get">` reading/writing URL search params, so filtering
  works via ordinary navigation with zero client-side JS (Next 16 App
  Router Server Components read `searchParams` directly). Honest empty
  state: distinguishes "no signals match these filters" from "signals
  exist but none has a closed trade yet" rather than one generic "empty."
- **AI Insights page** (`/ai-insights`): surfaces `reporting.
  plain_language_summary.explain_full_trade_review()`'s stored text
  verbatim — added `approval_summary` to `JournalEntry`/`JournalEntryOut`
  (it was already persisted on `PaperTrade`, Milestone 4, just never
  surfaced). **Real, load-bearing limitation surfaced rather than
  patched over**: that text is ONLY generated and stored when a
  `PaperTrade` is actually created — i.e. the risk engine approved a
  proposal AND a human was then asked to approve/decline it via
  `paper_trading/engine.py`. It is never reconstructed after the fact for
  a signal that didn't reach that stage, because the risk metrics it was
  built from (budget usage AT THAT TIME) weren't separately persisted on
  `Signal` — approximating them from current state would silently show
  the wrong numbers as if they were historical. As of this milestone
  there are 0 real `paper_trades`, so the page's honest fallback (explains
  why no stored review exists, shows what IS on record for that signal)
  is what actually renders today, not a placeholder — verified via
  screenshot.
- **System Health page** (`/system-health`): new `GET /system/health`
  reports what's genuinely checkable live (DB connectivity via a real
  query, latest persisted candle/signal timestamps) alongside two fields
  that are hardcoded `False` in the response itself, not just described
  as caveats in prose: `retry_events_tracked` and
  `paper_engine_heartbeat_tracked`. Neither is persisted anywhere in this
  system — `okx_client.py`'s retries are transient and in-process, and
  `paper_trading/engine.py` is a separate manually-run process with no
  heartbeat mechanism. The page shows amber "not tracked" indicators with
  the real reason, rather than a fabricated green checkmark for either.

**Verified visually, same standard as the first batch** — the browser
tool needed a `wait` before `screenshot` worked reliably this round
(same intermittent flakiness as before); all four pages confirmed
rendering real data correctly: actual `RiskConfig` values and budget
bars at their real (zero) usage, the two real journal entries filterable
by risk verdict, the honest AI Insights fallback explaining why no
stored review exists for the latest signal, and System Health's real
green connectivity dots alongside its honest amber "not tracked"
indicators.

## Real retry/heartbeat tracking for System Health (follow-up fix)

The two hardcoded-`False` System Health fields above (`retry_events_tracked`,
`paper_engine_heartbeat_tracked`) were a genuine, correctly-surfaced gap at
the time — but both are now closed with real, persisted signal instead of
prose caveats.

**Two new tables** (`db/models.py`, migration
`b958ebd1a9d1_add_retry_events_and_engine_heartbeats_`):
- `retry_events` — one row per retry attempt: `occurred_at`, `source`
  (`"okx"`), `request_desc`, `attempt_number`/`max_attempts`,
  `delay_seconds` (backoff before the NEXT attempt; `0` on the final,
  exhausted attempt), `exception_type`, `exception_message`.
- `engine_heartbeats` — one row per poll cycle: `engine_name`
  (`"paper_trading"`), `checked_in_at`, `symbol`, `detail`.

**Retry instrumentation** (`data/okx_client.py`): the existing
exponential-backoff retry loop in `get_klines()` (Milestone 4 reliability
fix) now calls a `_log_retry_event()` helper on every attempt, success or
not. That helper lazy-imports `db.session`/`db.repository` (so importing
`okx_client.py` doesn't itself require a configured DB) and swallows ALL
exceptions from the logging path itself — a logging failure must never be
able to break the actual data-fetching retry it's trying to record.

**Heartbeat instrumentation** (`paper_trading/engine.py`): `run_once()`
writes a heartbeat row as the very FIRST action in the cycle, before any
fetch or strategy logic. This is deliberate: it means liveness is proven
even when the rest of the cycle later raises (e.g. during an OKX outage),
because the write already committed.

**Real, non-fabricated health signals** (`api/routes/system.py`):
- `retry_health`: `"elevated"` if more than `RETRY_ELEVATED_THRESHOLD` (5)
  retry events occurred in the last `RETRY_LOOKBACK_MINUTES` (60) minutes,
  else `"clean"`. A count of recent events, not a guess.
- `paper_engine_status`: derived from elapsed time since
  `get_latest_heartbeat()`'s timestamp vs. the configured poll interval
  (`POLL_INTERVAL_SECONDS` = 900s / 15 min): `"not_running"` if no
  heartbeat ever exists; `"running"` if the last check-in is within 2x the
  poll interval (30 min — `HEARTBEAT_STALE_MULTIPLIER`); `"stale"` if
  older than that but within 24h; `"not_running"` again beyond 24h. The 2x
  multiplier gives one missed cycle of slack before flagging staleness,
  rather than flagging on the very first late poll.

**Verified against real activity, not synthetic mocks**: at the time of
this fix, `www.okx.com` genuinely failed to resolve (a real DNS/network
outage, confirmed independently via `socket.gethostbyname`) — so the
retry path was exercised by calling `OKXClient.get_klines()` with zero
mocking and letting all 4 real attempts fail naturally, logging 4 genuine
retry events with correct attempt numbers, backoff delays (1s/2s/4s/0s),
and exception details. All three `paper_engine_status` branches were
confirmed to compute correctly: `"running"` from a real fresh heartbeat,
`"not_running"` from an empty table, and `"stale"` by temporarily
isolating a synthetic 35-minutes-old row as the latest (the genuinely
fresh row was briefly removed to test this branch in isolation, then a
real `run_once()` call was made again afterward to restore an authentic
"running" state — no synthetic data was left in the DB).

The System Health page (`frontend/src/app/system-health/page.tsx`) now
renders a "Paper Trading Engine" panel (status dot + precise detail
text + last-checked-in timestamp) and an "OKX Retry Health" panel (health
verdict + a table of the last 20 real retry events), replacing the old
"Honest Gaps — Not Tracked Yet" panel entirely — both are confirmed live
via screenshot showing real data (16 genuine retry events from the OKX
outage above, a "running" heartbeat from ~6 minutes prior).

## Additional strategy modules (Milestone 7)

Per MASTER_PLAN.md Milestone 7: breakout, pullback, mean-reversion, and
range-trading strategies, each implemented against `strategies/base.py`'s
`Strategy` ABC and independently backtested + held-out validated —
nothing assumed profitable until proven, same bar as
`TrendContinuationBOS`'s EMA21 filter.

**New infrastructure**: `db.repository.get_candles()` loads already-
persisted candle history back into a DataFrame, so this milestone's
backtesting runs entirely off the ~5yr of BTCUSDT 4H history already in
Postgres (from prior milestones' polls/runs) rather than depending on
live OKX access. `backtest/validate_milestone7.py` is the reusable
validation runner: it runs ONE full-history backtest per strategy (so
every indicator gets proper warmup), then splits the resulting CLOSED
TRADES by `entry_time` into in-sample (everything before the most recent
365 days) and held-out (the most recent 365 days) — the held-out group's
equity curve is replayed fresh from `starting_balance` over just its own
trades, not sliced out of the full 5yr curve, so its drawdown reflects
"if this were the only trading you'd done" rather than a snapshot shaped
by years of prior trades. A strategy is only reported "validated" if the
held-out group shows genuine positive expectancy with at least 5 trades.

**Breakout** (`strategies/breakout.py`) — Donchian-channel break of the
prior 20-bar range (current bar's own high/low excluded from the channel,
so it's a genuine break of the PRIOR range) with an ATR-expansion
conviction filter, confirmed only by rejecting RSI-extreme entries (no
regime gate — a breakout is exactly the mechanism by which `sideways`
transitions into a trend, so excluding `sideways` would exclude the
strategy's own reason for existing). Deliberately independent of the
swing/BOS machinery `TrendContinuationBOS` uses — it fires on the range→
trend transition itself, not on confirmation of an already-established
trend.

**Result: NOT VALIDATED.** Full period (BTCUSDT, 5yr 4H, 126 trades):
40.5% win rate, +0.214R expectancy. In-sample alone (everything before
the most recent 365 days, 99 trades): +0.303R — looks like a real edge.
Held-out (most recent 365 days, genuine out-of-sample, 27 trades): win
rate drops to 29.6%, expectancy **flips to -0.111R**. Unlike the EMA21
filter (which stayed negative in the same direction both in-sample and
held-out — a weakened-but-consistent signal), this is a full sign flip:
the full-period/in-sample positive number was substantially an artifact
of the specific years backtested, not a property that generalizes
forward. Regime breakdown shows most entries (62/126) landing in the
`sideways` classification at entry time — mechanically expected, since a
fresh range breakout is often still classified `sideways` by the
20-bar-EMA-slope regime classifier before the slope catches up.

Kept in the codebase (not deleted) as a base for future iteration, same
"pause, don't delete" precedent as ETH — see `strategies/breakout.py`'s
own docstring for candidate revision directions (requiring
`TrendState.RANGE` specifically, or excluding the worst-performing
`strong_bear_trend` bucket). Not registered in `strategies/registry.py`
or exposed on the frontend Strategies page while unvalidated.

**Pullback** (`strategies/pullback.py`) — requires an already-established
trend (`classify_trend` says UPTREND/DOWNTREND, the same swing sequencing
`TrendContinuationBOS` uses), then a pullback to/through EMA21 on the
prior bar followed by a reclaim of EMA21 on the current bar ("buy the dip
in an uptrend," symmetric for downtrends). Gated to genuinely trending
regimes only (`strong_bull_trend`/`weak_bull_trend`/`strong_bear_trend`).

**Result: NOT VALIDATED.** Full period (38 trades): 31.6% win rate,
expectancy **-0.053R** — already net negative before any held-out split.
In-sample alone (31 trades): -0.032R. Held-out (most recent 365 days, 7
trades): -0.143R. This is a DIFFERENT failure shape than Breakout's:
Breakout had a real in-sample edge that didn't generalize forward
(overfitting); Pullback never had an edge in-sample OR held-out, pointing
at the entry logic itself lacking edge here rather than a generalization
failure. 32 of 38 trades landed in `weak_bull_trend` (-0.062R, the
dominant bucket); the other two regime buckets have only 3 trades each,
too few to read anything into individually. Held-out sample (7 trades) is
below this project's own reliability bar, but its direction agrees with
the larger in-sample slice, so this isn't just small-sample noise.
**Confidence caveat**: the full-period sample itself is small (38 trades
total vs. Breakout's 126) — the directional consistency across slices is
meaningful, but treat "lacks edge" as a reasonable working conclusion
from limited evidence, not a statistically strong one.

Kept in the codebase (not deleted), not registered in
`strategies/registry.py` or exposed on the frontend — see
`strategies/pullback.py`'s own docstring for candidate revision
directions (a minimum ATR-scaled pullback depth instead of "any EMA
touch," or multi-bar reclaim confirmation instead of a single-bar cross).

**Mean-reversion** (`strategies/mean_reversion.py`) — close at or beyond
a Bollinger Band extreme (2σ, 20-period) with RSI confirming the same
extreme (< 30 for long, > 70 for short), hard-gated to the `sideways`
regime only (every other regime rejected outright — fading a real trend
because RSI/BB read "overbought" is exactly the wrong idea to trade).

**Result: NOT VALIDATED — tested twice, against two different exits.**
Original run (fixed 2.0R target, shared with every other strategy):
full period (132 trades) -0.114R, in-sample (103 trades) -0.068R,
held-out (365 days, 29 trades) **-0.276R**.

**Re-tested after widening `Strategy.compute_take_profit()`** (see below)
to target `bb_mid` with a fixed-2.0R fallback when the band sits on the
wrong side of entry or closer than the stop distance — same 132 trades
(targeting a different price doesn't change which bars enter): full
period -0.068R (up from -0.114R), in-sample **-0.011R** (up from -0.068R,
nearly break-even), held-out **-0.27R** (essentially unchanged from
-0.276R). `avg_win_r` barely moved off 2.0 (2.02–2.09R across slices) —
a band-touching entry sits ~2 standard deviations from `bb_mid` by
construction, typically FARTHER than the old fixed 2R target, not closer,
so the fixed-R fallback was rarely needed.

**The exit-logic mismatch was real and measurable (in-sample improved
0.057R once removed) — but fixing it did not validate the strategy.**
Held-out expectancy is unchanged in every way that matters. This is
exactly the outcome held-out validation exists to catch: an
in-sample-only improvement (the exit fix) that didn't survive contact
with unseen data. The regime gate is still doing exactly what it was
built to do (100% of trades land in `sideways`), so this remains a
genuine "the entry condition itself lacks an edge in its own target
regime" result, not a stale-exit artifact. Kept in the codebase, not
registered in `strategies/registry.py` or exposed on the frontend.

**Cross-cutting finding, not per-strategy trivia (UPDATE below — this was
tested for Mean-reversion and the confound turned out not to be the
whole story): all four strategies originally shared the same fixed 2:1
reward:risk exit, inherited unchanged from `TrendContinuationBOS`.** That
target was never independently chosen for Breakout/Pullback/
Mean-reversion/RangeTrading — it was tuned around trend-continuation
behavior specifically (a BOS entry riding an established trend to a 2R
extension) and simply reused for interface consistency. Mean-reversion's
own diagnosis flagged this directly: a reversion trade is a bet on a
bounce back to the band's midline, a smaller expected move than a full
trend extension, so a 2R target sized for trend-following may be causing
genuine winning bounces to reverse back through break-even before ever
reaching it.

**Resolution (see the Interface widening section below): this was tested
for Mean-reversion, and the confound was real but not decisive.**
`Strategy.compute_take_profit()` was widened to receive the live window,
Mean-reversion was given a genuine `bb_mid` target, and its in-sample
expectancy DID improve (-0.068R → -0.011R, nearly break-even) — the
confound was measurable, not imagined. But held-out expectancy barely
moved (-0.276R → -0.27R), so the strategy is still NOT VALIDATED: the
entry condition itself lacks a genuine out-of-sample edge, independent of
which exit it's paired with.

The same logic, untested so far, still applies to Breakout and Pullback:
neither is a trend-continuation setup either (Breakout catches a
range→trend transition before structure confirms it; Pullback catches a
retracement, not a fresh extension), so their entries have not actually
been re-tested against an exit shaped for what THEY are. Given
Mean-reversion's result, the realistic expectation for a similar re-test
on Breakout/Pullback is a similar outcome — some in-sample movement,
held-out conclusion probably unchanged — but that's an expectation, not a
finding; neither has actually been re-tested. The interface change itself
is already built and available for either, cheaply, whenever there's
appetite. RangeTrading's bigger re-test (targeting the opposite S/R zone,
which needs `swings` threaded through too) remains deliberately deferred
— see the Interface widening section for why.

**Range trading** (`strategies/range_trading.py`) — the structural
counterpart to Mean-reversion's statistical one: a bounce off a
support/resistance zone built from the shared swing engine
(`build_sr_zones`), hard-gated to `TrendState.RANGE` (from the swing
HH/HL/LH/LL sequence) rather than Mean-reversion's `sideways` REGIME
(EMA-slope/ATR derived) — two independently-derived "is this ranging?"
signals that can and do disagree on individual bars.

**Result: NOT VALIDATED — but the closest of the four to passing.** Full
period (627 trades, by far the largest sample built in this milestone):
37.2% win rate, expectancy +0.115R. In-sample (489 trades): +0.153R.
Held-out (most recent 365 days, 138 trades): **-0.022R** — technically
negative, so it fails the file's own bar, but close to break-even, not a
clear negative like Pullback (-0.143R) or Mean-reversion (-0.276R). Same
directional shape as Breakout's failure (positive in-sample, negative
held-out) but far milder — "didn't survive out-of-sample," not
"inverted." Held-out max drawdown (-40.86%) is a real concern
independent of the expectancy discussion — the largest drawdown of any
strategy/slice in this milestone.

Worth stating plainly rather than glossing over: the regime breakdown
shows this strategy's actual positive expectancy concentrated in
`weak_bull_trend` (+0.200R, 275 trades) and `strong_bull_trend` (+0.500R,
16 trades) — NOT in `sideways` (+0.034R, barely positive, its largest
bucket at 322 trades), which is where a genuine range-trading edge would
be expected to show up most cleanly. This is the TrendState-vs-Regime
disagreement in practice: many `TrendState.RANGE` bars occur during
periods the EMA-slope regime classifier still calls a bull trend
(consolidation/whipsaw within an uptrend), not true range-bound sideways
action — so whatever edge exists here may not actually be "range trading"
in the sense the label implies. Same shared-2.0R-target caveat as the
other three applies here too.

Kept in the codebase (not deleted), not registered in
`strategies/registry.py` or exposed on the frontend Strategies page while
unvalidated.

## Interface widening: per-strategy take-profit logic

`Strategy.compute_take_profit(setup, stop_price)` was widened to
`compute_take_profit(setup, stop_price, window)` so a strategy CAN target
something other than a fixed reward:risk multiple (e.g. Mean-reversion's
`bb_mid`) when its own trade shape calls for it — see Mean-reversion's
result above for why this mattered and what it did/didn't change.

**What actually changed:**
- `strategies/base.py`'s abstract signature, both call sites
  (`backtest_engine.py`, `trade_proposal.py`), and a one-line signature
  update (no logic change) on every strategy that stays fixed-R:
  `TrendContinuationBOS`, `Breakout`, `Pullback`, `RangeTrading`.
- Mean-reversion's real logic: target `bb_mid`, falling back to the fixed
  2.0R target when `bb_mid` is on the wrong side of entry or closer than
  the stop distance (a sub-1:1 floor, regardless of win rate).
- **A correctness issue found mid-implementation, not part of the
  original plan**: `Strategy.check_exit()`'s win branch used to hardcode
  `self.reward_risk` as the realized R-multiple, which was only ever true
  because every existing strategy's target was exactly
  `stop_dist * reward_risk` away. Once a target can be something else
  (`bb_mid`), the realized R-multiple on a win depends on `entry_price`
  too — so `check_exit()` was also widened to receive it
  (`check_exit(direction, entry_price, stop_price, target_price, bar)`),
  with the same one-line signature update on every non-Mean-reversion
  strategy. The loss case is unaffected either way — stop distance
  defines "1R" risk by construction, so a stop-out is always exactly
  -1.0 regardless of the target.

**Already-open positions are unaffected, verified not assumed**: an open
`PaperTrade`'s `stop_price`/`target_price` are computed exactly once (in
`build_proposal()`, before human approval) and persisted as plain floats;
`_check_open_position()` in `paper_trading/engine.py` reads those stored
values directly from the DB on every subsequent poll and calls only
`check_exit()` — never `compute_take_profit()` again. Confirmed against
paper trade #6 (open at the time of this change) before making any edit.

**Regression check on `TrendContinuationBOS` — the one currently-live
strategy**: ran the full 5yr backtest before and after this change (via
`git stash`/`git stash pop` to get a clean before/after) and diffed every
field of every one of its 126 trades (entry/exit price and time, regime,
all six diagnostics, position sizing, R-multiple). Byte-for-byte
identical. The wider signatures don't change its behavior at all.

**Deliberately deferred**: RangeTrading's equivalent re-test (targeting
the opposite S/R zone) needs `swings` threaded through
`compute_take_profit()` too — a bigger change (zone-matching must agree
with what `check_entry()` saw, which needs care to get right) — held off
until there's a decision on whether Mean-reversion's result (confound
real but not decisive) makes that additional effort worth it before
Milestone 7 closes.

## Milestone 7 close-out

**Status: closed.** Four new strategies built against the `Strategy` ABC,
each independently backtested and held-out validated with the same rigor
as `TrendContinuationBOS`'s own EMA21 filter — full period, in-sample,
and held-out (most recent 365 days) reported separately, honestly, per
strategy:

- **Breakout** — overfit: real in-sample edge (+0.303R) that inverted
  held-out (-0.111R).
- **Pullback** — no edge anywhere: negative in-sample AND held-out,
  smallest sample (38 trades) of the four.
- **Mean-reversion** — no edge, confirmed twice: negative under the
  original shared fixed-R exit, and STILL negative held-out
  (-0.27R) after being given a bb_mid target actually shaped for its own
  trade type. The exit-logic confound was real (in-sample improved
  measurably) but not decisive — the entry condition itself doesn't hold
  up out-of-sample either way.
- **Range trading** — closest of the four to passing (held-out -0.022R,
  near break-even, largest sample at 627 trades) but still fails the
  validation bar under the shared fixed-R exit.

**None are registered in `strategies/registry.py` or exposed on the
frontend Strategies page.** `TrendContinuationBOS` remains the only
validated, live strategy — unchanged and unaffected by any of this
milestone's work (see the byte-for-byte regression check above, and
PaperTrade #6's confirmed-unaffected stop/target values, re-verified
against its originally-recorded values one final time before this
close-out: `stop_price=76341.37`, `target_price=81354.46`,
`entry_fill_price=78051.4062`, `position_size=5.984337` — identical
across every checkpoint taken during this milestone's interface changes).

**Why RangeTrading's bigger exit re-test was not pursued further**:
Mean-reversion is the direct, controlled test of the underlying question
("does a mismatched fixed-R exit explain a strategy's failure?") — its
entry and regime gate were unchanged, ONLY the exit changed, and the
held-out conclusion didn't move. That result is evidence about the
GENERAL question, not just about Mean-reversion specifically: fixing
exit logic alone did not reliably rescue an entry that lacks real edge in
the one case actually tested. RangeTrading's exit fix is more expensive
than Mean-reversion's was (it needs `swings` threaded through
`compute_take_profit()` for zone-matching, not just a `window` lookup)
and RangeTrading is already the closest-to-passing of the four under the
existing exit — meaning it has the least room for an exit fix to move
the needle relative to its effort cost, not the most. Given that,
spending the bigger effort here is not the highest-value next step
available, so it was held off rather than pursued reflexively just
because the interface now supports it. This is a judgment call based on
one data point (Mean-reversion), not a proof that RangeTrading's exit
mismatch is definitely irrelevant — worth revisiting if a future
milestone's work makes the opposite-zone target cheap to add for other
reasons (e.g. if `swings` ends up threaded through for something else
first).

**What now exists for future strategy research**: `db.repository.
get_candles()` (backtest off persisted history, no live exchange
dependency), `backtest/validate_milestone7.py` (reusable full/in-sample/
held-out validation runner, parametrized by strategy name), and a
`Strategy.compute_take_profit()`/`check_exit()` interface that supports
a genuine per-strategy exit, not just a shared fixed-R one — all
reusable for any future strategy idea, not specific to these four.

## Architecture philosophy
Deterministic core, LLM synthesis layer (Option 3 from planning discussion),
evolving toward a proper multi-agent system (Option 2 / LangGraph-style)
once the deterministic core is validated. Concretely:

- Market structure detection, indicators, regime classification, backtesting,
  and position sizing are all **plain deterministic Python**. No LLM
  involved in deciding whether price made a higher high — that must always
  be correct, fast, and testable.
- An **LLM synthesis layer** sits on top only to: read the deterministic
  outputs (structure state, regime, indicator readings, backtested stats
  for the matched setup type) and turn them into a clear, human-readable
  trade proposal with reasoning. It does NOT invent numbers — it narrates
  numbers the deterministic core already computed.
- This synthesis layer will evolve into a multi-agent system later
  (structure agent → regime agent → strategy agent → risk agent → proposal
  agent), which doubles as practice for the LangGraph capstone work in the
  separate RAG/agent learning roadmap.

## Phased build plan

### Phase 1 (current) — Foundation
1. Data ingestion: pull OHLCV (daily + 4H) from Bybit for BTC/USDT, ETH/USDT.
2. Market structure engine:
   - Swing high/low detection
   - HH/HL/LH/LL sequence tracking → trend state (up/down/range)
   - Support/resistance zone identification, S→R flip detection
   - Liquidity concepts: equal highs/lows, session/previous-day high/low
   - Break of structure (BOS) / change of character (CHoCH) detection
3. Regime classifier: strong bull / weak bull / range / high-volatility /
   strong bear / panic-recovery, derived from trend slope + ATR + range
   width — NOT a black box, each label traceable to the numbers behind it.
4. Core indicator set (lean, not a collector's set):
   - EMA (trend filter)
   - RSI or Stochastic (momentum)
   - ATR (volatility, used for stop-loss distance)
   - Optional: Bollinger Bands, volume-based confirmation
5. Backtest engine: run structure + indicator logic against 1-2 years of
   historical BTC/ETH data. Output: win rate, avg win/loss, max drawdown,
   expectancy — per setup type. This is what makes "80% chance of profit"
   type statements honest instead of invented.
6. Trade proposal object: structured output (setup type, entry, stop,
   target, position size from risk %, backtested stats for that setup
   type). This is what the human reviews before approving.

### Phase 2 — Strategy modules + human approval loop
- Strategy modules gated by regime (e.g. trend-following only activates
  when regime = trending; mean-reversion only in range regime).
- Human-in-the-loop approval flow for every trade.
- LLM synthesis layer: turns Phase 1 deterministic outputs into a clear
  proposal narrative.

### Phase 3 — Context layers
- On-chain metrics (SOPR, MVRV, NUPL, exchange flows) as a slow-moving
  bias filter, not per-trade signal.
- Macro context (Fed rates, CPI, DXY) as a bias filter.
- Funding rate / open interest / long-short skew as sentiment context.

### Phase 4 — Testnet → small live capital
- Bybit testnet validation of execution mechanics.
- Live trading starting with a small fraction of capital.
- Multi-agent evolution of the synthesis layer (LangGraph).

## Explicitly out of scope for now
- Intraday/scalping timeframes.
- High leverage.
- Fully unattended live execution (human approval required every trade,
  reassess only after Phase 1-4 track record justifies it).
- Guaranteed/fixed-timeline return targets — none of this design promises
  a specific return by a specific date, because no honest trading system
  can.

## Repo structure
```
crypto-swing-bot/
├── data/          # Bybit data ingestion (OHLCV, funding, etc.) — okx_client.py is a backtesting-only stand-in, see Style
├── structure/     # Market structure engine (swings, trend, S/R, liquidity)
├── indicators/     # Technical indicators
├── regime/        # Regime classifier
├── backtest/       # Backtesting engine + historical data
├── proposals/      # Trade proposal generation (deterministic + LLM synthesis)
├── strategies/     # Strategy interface + concrete strategies (Milestone 3)
├── risk/           # Risk Management Engine — active APPROVE/REJECT gate on proposals (Milestone 2)
├── paper_trading/  # Paper trading engine — human-approved simulated fills (Milestone 4)
├── journal/        # Trading journal query layer over signals + paper_trades (Milestone 5)
├── api/            # FastAPI routes exposing the journal (Milestone 5)
├── db/             # SQLAlchemy models + repository (persistence layer, Milestone 1)
├── agents/         # Future: LangGraph multi-agent orchestration (Phase 4)
├── config/         # Risk %, pairs, timeframes, API keys (via env vars)
├── tests/          # Unit tests for structure/indicator/backtest logic
├── frontend/       # Next.js dashboard (Milestone 6) — Dashboard/Positions/Orders/Strategies/Backtesting
├── docs/           # This file + further design notes
└── logs/           # Trade logs, equity curve, backtest reports
```
