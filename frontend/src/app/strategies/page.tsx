import { Panel } from "@/components/Panel";
import { StatTile } from "@/components/StatTile";
import { listBacktestRuns, listStrategies } from "@/lib/api";
import { formatPct, formatR } from "@/lib/format";

export default async function StrategiesPage() {
  const strategies = await listStrategies();
  const runsBySymbol = await Promise.all(
    strategies.map((s) => listBacktestRuns({ symbol: s.symbols[0], limit: 1 })),
  );

  return (
    <div className="flex flex-col gap-4">
      {strategies.map((s, i) => {
        const latestRun = runsBySymbol[i]?.[0];
        return (
          <Panel key={s.name} title={s.name}>
            <div className="flex flex-col gap-3 p-3">
              <p className="text-sm text-primary">{s.description}</p>

              <div className="flex flex-wrap gap-2">
                {s.symbols.map((sym) => (
                  <span
                    key={sym}
                    className="rounded-[3px] border border-border px-2 py-0.5 font-mono text-xs text-muted"
                  >
                    {sym}
                  </span>
                ))}
              </div>

              <div className="border-t border-border pt-3">
                <h3 className="mb-2 font-mono text-[0.7rem] uppercase tracking-wider text-muted">
                  Parameters
                </h3>
                <div className="flex flex-wrap gap-4 font-mono text-sm">
                  {Object.entries(s.parameters).map(([key, value]) => (
                    <div key={key} className="flex items-baseline gap-1.5">
                      <span className="text-muted">{key}:</span>
                      <span className="text-primary">{JSON.stringify(value)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {latestRun && (
                <div className="border-t border-border pt-3">
                  <h3 className="mb-2 font-mono text-[0.7rem] uppercase tracking-wider text-muted">
                    Latest backtested performance ({latestRun.symbol})
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4">
                    <StatTile label="Trades" value={String(latestRun.summary.total_trades)} />
                    <StatTile label="Win Rate" value={formatPct(latestRun.summary.win_rate_pct)} />
                    <StatTile
                      label="Expectancy"
                      value={formatR(latestRun.summary.expectancy_r)}
                      tone={latestRun.summary.expectancy_r >= 0 ? "green" : "red"}
                    />
                    <StatTile label="Avg Win / Loss" value={`${formatR(latestRun.summary.avg_win_r)} / ${formatR(latestRun.summary.avg_loss_r)}`} />
                  </div>
                </div>
              )}
              {!latestRun && (
                <p className="border-t border-border pt-3 text-xs text-muted">
                  No backtest run recorded yet for this strategy.
                </p>
              )}
            </div>
          </Panel>
        );
      })}
    </div>
  );
}
