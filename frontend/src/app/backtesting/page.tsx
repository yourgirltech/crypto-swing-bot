import { Panel } from "@/components/Panel";
import { CumulativeRChart } from "@/components/charts/CumulativeRChart";
import { getCumulativeRCurve, listBacktestRuns } from "@/lib/api";
import { formatDateTime, formatPct, formatR } from "@/lib/format";

export default async function BacktestingPage() {
  const runs = await listBacktestRuns({ limit: 50 });
  const latestRun = runs[0];
  const cumulativeR = latestRun ? await getCumulativeRCurve(latestRun.id) : [];

  return (
    <div className="flex flex-col gap-4">
      {latestRun && (
        <Panel title={`Cumulative R — Run #${latestRun.id} (${latestRun.symbol}, ${formatDateTime(latestRun.run_at)})`}>
          <p className="border-b border-border px-3 py-2 text-xs text-muted">
            Cumulative R-multiple, not a ₦ equity curve — per-trade position size was never persisted
            for historical backtest_trades rows, so a dollar figure here would not match what this run
            actually computed. R-multiple is position-size-independent, so this is exact.
          </p>
          {cumulativeR.length === 0 ? (
            <p className="p-4 text-sm text-muted">No closed trades in this run.</p>
          ) : (
            <CumulativeRChart points={cumulativeR} />
          )}
        </Panel>
      )}

      <Panel title={`Backtest Runs (${runs.length})`}>
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          Historical drawdown isn&apos;t shown for these runs — per-trade position size wasn&apos;t
          persisted before the Milestone 4 sizing fix, so it can&apos;t be reconstructed honestly.
        </p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Run At</th>
                <th>Symbol</th>
                <th>Timeframe</th>
                <th>Data Source</th>
                <th>Date Range</th>
                <th>Trades</th>
                <th>Win Rate</th>
                <th>Avg Win / Loss</th>
                <th>Expectancy</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-muted">
                    No backtest runs recorded yet.
                  </td>
                </tr>
              )}
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{formatDateTime(r.run_at)}</td>
                  <td>{r.symbol}</td>
                  <td className="text-muted">{r.timeframe}</td>
                  <td className="text-muted uppercase">{r.data_source}</td>
                  <td className="text-muted">
                    {formatDateTime(r.date_range_start).split(",")[0]} –{" "}
                    {formatDateTime(r.date_range_end).split(",")[0]}
                  </td>
                  <td>{r.summary.total_trades}</td>
                  <td>{formatPct(r.summary.win_rate_pct)}</td>
                  <td>
                    {formatR(r.summary.avg_win_r)} / {formatR(r.summary.avg_loss_r)}
                  </td>
                  <td className={r.summary.expectancy_r >= 0 ? "text-green" : "text-red"}>
                    {formatR(r.summary.expectancy_r, 3)}
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
