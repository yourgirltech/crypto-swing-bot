"""
Central configuration for the trading bot.
Nothing trade-critical should be hardcoded elsewhere — change values here.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskConfig:
    account_size_ngn: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0        # % of account risked per trade
    max_daily_loss_pct: float = 3.0        # circuit breaker: stop trading for the day
    max_weekly_loss_pct: float = 6.0       # circuit breaker: stop trading for the week
    max_open_positions: int = 2            # cap concurrent exposure
    max_leverage: float = 1.0              # 1.0 = spot-like, no leverage, to start
    # Added for Milestone 2 (risk/risk_engine.py) — confirmed with user
    # 2026-08-25 rather than picked silently, per the no-silent-risk-change rule.
    # RECALIBRATED 2026-08-25 (Milestone 4): 20% was miscalibrated as a
    # genuine backstop -- given risk_per_trade_pct=1% and this strategy's
    # typical ATR-based stop distance, 96% of the 126 backtested BTC trades
    # would size down under a 20% cap, to a MEAN effective risk of ~0.46%
    # (not 1%) -- meaning 20% was the routine sizing mechanism, not a rare
    # backstop. Fixed properly via risk/position_sizing.py's dual-constraint
    # sizing (position sizing takes the min of risk-based size and this
    # notional cap, sizing DOWN rather than being rejected outright or
    # requiring the cap to be loosened) -- see strategies/trend_continuation_
    # bos.py / backtest_engine.py / proposals/trade_proposal.py. 85% is the
    # real gap in the data: every one of the 126 backtested trades' true
    # (uncapped) notional size tops out at 79.38%, then jumps straight to
    # 102.48%+ (which max_leverage=1.0 already rejects on its own) -- nothing
    # in between. At 85%, only those same pre-existing max_leverage outliers
    # (4.0% of trades) ever hit this cap; every normal trade sizes at its
    # full risk_per_trade_pct target, as intended.
    max_position_size_pct: float = 85.0        # per-trade notional cap, % of account equity
    # max_portfolio_exposure_pct / max_correlated_exposure_pct were 85%
    # (2026-08-25) ONLY because BTC was the sole active symbol and no
    # second concurrent position was ever possible -- "portfolio exposure"
    # and "correlated exposure" collapsed to "this one position's own
    # notional," identical to what max_position_size_pct already measures.
    # That comment explicitly flagged this as temporary and required
    # re-derivation "the moment ETH resumes trading" -- this is that
    # re-derivation, ahead of ETH actually going live (Breakout validated
    # on ETH per Milestone 7/10; MARKET.pairs is still BTC-only as of this
    # value change -- see strategies/registry.py/docs/ARCHITECTURE.md's
    # Milestone 10 section for what's still not wired in).
    #
    # *** RECALIBRATED 2026-08-26 to 90%, using real data, same "run
    # *** uncapped, find the natural gap" methodology as
    # *** max_position_size_pct's own derivation above -- not guessed.
    # *** backtest/combined_portfolio_backtest.py ran TrendContinuationBOS-
    # *** on-BTC concurrent with Breakout-on-ETH as ONE real portfolio
    # *** (shared balance, both positions tracked simultaneously) across
    # *** their aligned 5yr 4H history, with these two caps set to an
    # *** effectively-uncapped 1000% to observe the natural distribution.
    # *** Result: 49 genuine concurrent entries (one asset entering while
    # *** the other was already open). Combined notional -- both
    # *** positions' notional together, as % of equity -- clustered
    # *** continuously from 27.45% up to ~88.90%, then jumped straight to
    # *** 107.61% and 141.45% (two outliers), nothing in between -- the
    # *** same shape of gap that justified 85% for max_position_size_pct.
    # *** 90% sits in that gap: above the natural cluster ceiling (so it
    # *** doesn't clip real, reasonable concurrent trades the way the old
    # *** 85% value clipped 3 of 48 real historical concurrent entries
    # *** under the CURRENT caps), below the outlier jump (so it still
    # *** backstops the two genuine over-100%-of-equity scenarios that
    # *** max_leverage=1.0 alone would NOT catch, since that check is
    # *** per-trade notional only, not combined across positions).
    # *** CONFIDENCE CAVEAT: 49 concurrent-entry observations is a much
    # *** smaller sample than the 126-trade sample behind
    # *** max_position_size_pct=85% -- the SHAPE of the gap (~89% cluster
    # *** ceiling, then a jump past 100%) is clear, but hold 90% loosely,
    # *** not as a precisely-optimized number. Re-derive again once real
    # *** paper-trading history with both positions concurrently open
    # *** actually accumulates, rather than trusting this backtested
    # *** estimate indefinitely.
    max_portfolio_exposure_pct: float = 90.0   # total notional across all open positions, % of account equity
    max_drawdown_pct: float = 15.0             # equity drop from peak that halts ALL new trades (kill switch);
                                                # deliberately above BTC's backtested max DD (-11.57%) as live-variance buffer
    max_correlated_exposure_pct: float = 90.0  # combined notional across one correlated_groups entry, % of account equity — see max_portfolio_exposure_pct's comment above; identical value for the same reason (BTC+ETH is the only correlated_groups entry and the only two traded assets)
    correlated_groups: List[List[str]] = field(default_factory=lambda: [["BTCUSDT", "ETHUSDT"]])
    # BTC+ETH treated as one correlated group. ETH is paused (see MarketConfig
    # below) so this has nothing real to bite on yet -- see the max_correlated_
    # exposure_pct comment above for why its VALUE is 85% today and why that
    # must be re-derived, not assumed, once ETH trading resumes.


@dataclass
class MarketConfig:
    # ETHUSDT REACTIVATED 2026-08-26 -- with Breakout, NOT TrendContinuationBOS.
    # TrendContinuationBOS itself is still net-unprofitable on ETH (-0.059R
    # over 118 trades as last verified; see strategies/trend_continuation_bos.py
    # -- losses are NOT uniform across regimes as originally characterized,
    # weak_bull_trend is actually strongly positive there, see
    # docs/ARCHITECTURE.md's btc_only_focus note) and is NOT assigned to ETH.
    # Breakout (Milestone 7, shelved on BTC as overfit) independently held-out
    # validates on ETH (held-out: 22 trades, +0.091R) -- see
    # strategies/breakout.py and docs/ARCHITECTURE.md's Milestone 10 section
    # for the full validation, the combined-portfolio backtest that checked
    # BTC+ETH concurrent exposure before this reactivation, and the
    # per-symbol-strategy mapping (strategies/registry.py's
    # STRATEGY_FOR_SYMBOL) that makes each symbol run its OWN assigned
    # strategy rather than one strategy applied uniformly. This activation
    # is paper trading only -- see paper_trading/engine.py; it serves as the
    # real-world validation period before any live-trading discussion.
    pairs: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    primary_timeframe: str = "240"    # 4H, Bybit kline interval string (minutes)
    context_timeframe: str = "D"      # Daily, for trend/structure context
    exchange: str = "bybit"
    category: str = "spot"            # "spot" | "linear" (futures/perps) — start spot


@dataclass
class StructureConfig:
    swing_lookback: int = 5           # bars each side to confirm a swing high/low
    equal_level_tolerance_pct: float = 0.15   # % tolerance for "equal" highs/lows


@dataclass
class IndicatorConfig:
    ema_fast: int = 21
    ema_slow: int = 50
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0


@dataclass
class BacktestConfig:
    history_days: int = 1825          # ~5 years of daily data
    starting_balance: float = 1_000_000.0
    slippage_pct: float = 0.05
    fee_pct: float = 0.1              # taker fee assumption, per side


RISK = RiskConfig()
MARKET = MarketConfig()
STRUCTURE = StructureConfig()
INDICATORS = IndicatorConfig()
BACKTEST = BacktestConfig()

# API credentials — never hardcode keys. Set these as environment variables.
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

# Local Postgres (see docker-compose.yml). Default matches that file's
# credentials so `docker compose up` + no .env just works for local dev.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://swingbot:swingbot@localhost:5433/swingbot")
