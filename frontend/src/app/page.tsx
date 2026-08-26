import { Panel } from "@/components/Panel";
import { StatTile } from "@/components/StatTile";
import { HumanDecisionStamp, OutcomeStamp, RiskStatusStamp } from "@/components/VerdictStamp";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { PriceChart } from "@/components/charts/PriceChart";
import { getAccountSummary, getCandles, getEquityCurve, getPerformanceStats, listJournalEntries } from "@/lib/api";
import { formatDateTime, formatNgn, formatPct, formatR } from "@/lib/format";

const PRIMARY_SYMBOL = "BTCUSDT";

export default async function DashboardPage() {
  const [account, performance, recent, equityCurve, candles] = await Promise.all([
    getAccountSummary(),
    getPerformanceStats(),
    listJournalEntries({ limit: 10 }),
    getEquityCurve(),
    getCandles({ symbol: PRIMARY_SYMBOL, limit: 180 }),
  ]);

  const latestSignal = recent[0];

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Portfolio Overview">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile label="Equity" value={formatNgn(account.account_equity)} />
          <StatTile
            label="Open Positions"
            value={`${account.open_positions_count}/${account.max_open_positions}`}
          />
          <StatTile label="Win Rate" value={formatPct(performance.win_rate_pct)} />
          <StatTile
            label="Expectancy (real.)"
            value={formatR(performance.expectancy_r_realistic)}
            tone={performance.expectancy_r_realistic >= 0 ? "green" : "red"}
          />
          <StatTile
            label="Total P&L"
            value={formatNgn(performance.total_pnl_ngn, { showSign: true })}
            tone={performance.total_pnl_ngn >= 0 ? "green" : "red"}
          />
          <StatTile label="Closed Trades" value={String(performance.total_closed_trades)} />
        </div>
      </Panel>

      <Panel title="Realistic vs. Ideal Expectancy">
        <div className="grid grid-cols-2">
          <StatTile
            label="Ideal (backtest-style)"
            value={formatR(performance.expectancy_r_ideal)}
            sub="Naive -1.0R / +reward_risk, no slippage or fees"
          />
          <StatTile
            label="Realistic (paper-simulated)"
            value={formatR(performance.expectancy_r_realistic)}
            tone={performance.expectancy_r_realistic >= 0 ? "green" : "red"}
            sub={`After ${formatNgn(performance.total_fees_ngn)} total simulated fees`}
          />
        </div>
      </Panel>

      <Panel title="Equity Curve">
        {equityCurve.length <= 1 ? (
          <p className="p-4 text-sm text-muted">
            No closed paper trades yet — the curve starts flat at the account baseline
            ({formatNgn(equityCurve[0]?.equity)}) until at least one real paper trade closes.
          </p>
        ) : (
          <EquityCurveChart points={equityCurve} />
        )}
      </Panel>

      <Panel title={`${PRIMARY_SYMBOL} Price Action (EMA 21 / EMA 50)`}>
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          Last-polled candles, not a live feed — this system polls on an interval (see Milestone 4), it
          does not stream real-time ticks.
          {latestSignal &&
            ` Reference lines mark the most recent signal's entry/stop/target (${latestSignal.setup_type}, ${latestSignal.direction}).`}
        </p>
        {candles.length === 0 ? (
          <p className="p-4 text-sm text-muted">No candles persisted yet for {PRIMARY_SYMBOL}.</p>
        ) : (
          <PriceChart
            candles={candles}
            markers={
              latestSignal
                ? {
                    entry_price: latestSignal.entry_price,
                    stop_price: latestSignal.stop_price,
                    target_price: latestSignal.target_price,
                    direction: latestSignal.direction,
                  }
                : undefined
            }
          />
        )}
      </Panel>

      <Panel title="Recent Activity">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Dir</th>
                <th>Regime</th>
                <th>Risk Verdict</th>
                <th>Human</th>
                <th>Outcome</th>
                <th className="text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-muted">
                    No signals generated yet.
                  </td>
                </tr>
              )}
              {recent.map((e) => (
                <tr key={e.signal_id}>
                  <td>{formatDateTime(e.generated_at)}</td>
                  <td>{e.symbol}</td>
                  <td>{e.setup_type}</td>
                  <td className={e.direction === "long" ? "text-green" : "text-red"}>
                    {e.direction.toUpperCase()}
                  </td>
                  <td className="text-muted">{e.regime}</td>
                  <td>
                    <RiskStatusStamp status={e.risk_status} />
                  </td>
                  <td>
                    <HumanDecisionStamp decision={e.human_decision} />
                  </td>
                  <td>
                    <OutcomeStamp outcome={e.outcome} />
                  </td>
                  <td
                    className={`text-right ${
                      e.pnl_ngn == null ? "text-muted" : e.pnl_ngn >= 0 ? "text-green" : "text-red"
                    }`}
                  >
                    {formatNgn(e.pnl_ngn, { showSign: true })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
