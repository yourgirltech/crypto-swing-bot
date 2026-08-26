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
    # max_portfolio_exposure_pct / max_correlated_exposure_pct RECALIBRATED
    # to 85% too (2026-08-25), same day as max_position_size_pct, for a
    # DIFFERENT and TEMPORARY reason -- read before ever changing ETH's
    # paused status or MARKET.pairs:
    #
    # *** These three values are only equal because BTC is the sole active
    # *** symbol AND max_open_positions effectively never allows two
    # *** concurrent BTC positions (paper_trading/engine.py won't open a
    # *** second position on an asset that already has one open). With
    # *** correlated_groups containing only one CURRENTLY-TRADED asset,
    # *** "portfolio exposure" and "correlated exposure" collapse to
    # *** "this one position's own notional" -- IDENTICAL to what
    # *** max_position_size_pct already measures. Confirmed via full
    # *** 126-trade backtest re-run: at the old 50%/30%, mean effective
    # *** risk was dragged down to 0.689% (vs the ~1% target) purely by
    # *** this coincidence, not a deliberate portfolio-risk decision.
    #
    # *** THE MOMENT ETH RESUMES TRADING (a second concurrent position
    # *** becomes real), max_correlated_exposure_pct (and, once
    # *** max_open_positions can actually reach 2, max_portfolio_exposure_pct
    # *** too) MUST be independently reassessed against real two-asset
    # *** combined-exposure data -- do NOT assume 85% still fits just
    # *** because it's already sitting there. This is a coincidence of
    # *** today's BTC-only reality, not a permanent design decision.
    max_portfolio_exposure_pct: float = 85.0   # total notional across all open positions, % of account equity
    max_drawdown_pct: float = 15.0             # equity drop from peak that halts ALL new trades (kill switch);
                                                # deliberately above BTC's backtested max DD (-11.57%) as live-variance buffer
    max_correlated_exposure_pct: float = 85.0  # combined notional across one correlated_groups entry, % of account equity
    correlated_groups: List[List[str]] = field(default_factory=lambda: [["BTCUSDT", "ETHUSDT"]])
    # BTC+ETH treated as one correlated group. ETH is paused (see MarketConfig
    # below) so this has nothing real to bite on yet -- see the max_correlated_
    # exposure_pct comment above for why its VALUE is 85% today and why that
    # must be re-derived, not assumed, once ETH trading resumes.


@dataclass
class MarketConfig:
    # ETHUSDT is PAUSED, not removed, as of the 2026-08-24 5-year backtest
    # review: the trend-continuation BOS setup lost money on ETH overall
    # (-0.065R expectancy over 138 trades), and critically the losses were
    # NOT concentrated in one regime (sideways: -0.385R, strong_bear_trend:
    # -0.400R) — they showed up across regimes. That pattern points to the
    # entry logic itself not suiting ETH's price behavior, not just a
    # regime-gating problem that a filter could fix. data/okx_client.py and
    # the rest of the pipeline still support ETH so it can be revisited
    # with different strategy logic later — it's just excluded from the
    # active backtest/proposal run for now.
    pairs: List[str] = field(default_factory=lambda: ["BTCUSDT"])
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
