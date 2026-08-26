import { BudgetBar } from "@/components/BudgetBar";
import { Panel } from "@/components/Panel";
import { StatTile } from "@/components/StatTile";
import { RiskStatusStamp } from "@/components/VerdictStamp";
import { getRiskState, listJournalEntries } from "@/lib/api";
import { formatDateTime, formatNgn, formatPct } from "@/lib/format";

export default async function RiskPage() {
  const [risk, recentVerdicts] = await Promise.all([
    getRiskState(),
    listJournalEntries({ limit: 20 }),
  ]);

  const dailyUsed = Math.max(0, -risk.daily_pnl_pct);
  const weeklyUsed = Math.max(0, -risk.weekly_pnl_pct);

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Configured Limits">
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          config/config.py&apos;s RiskConfig, read directly -- not editable from this dashboard.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          <StatTile label="Risk / Trade" value={formatPct(risk.risk_per_trade_pct)} />
          <StatTile label="Max Position Size" value={formatPct(risk.max_position_size_pct)} />
          <StatTile label="Max Portfolio Exposure" value={formatPct(risk.max_portfolio_exposure_pct)} />
          <StatTile label="Max Correlated Exposure" value={formatPct(risk.max_correlated_exposure_pct)} />
          <StatTile label="Max Leverage" value={`${risk.max_leverage.toFixed(1)}x`} />
          <StatTile label="Max Daily Loss" value={formatPct(risk.max_daily_loss_pct)} />
          <StatTile label="Max Weekly Loss" value={formatPct(risk.max_weekly_loss_pct)} />
          <StatTile label="Max Drawdown" value={formatPct(risk.max_drawdown_pct)} />
          <StatTile label="Max Open Positions" value={String(risk.max_open_positions)} />
        </div>
      </Panel>

      <Panel title="Current Usage Against Each Limit">
        <div className="grid grid-cols-1 divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
          <BudgetBar label="Daily Loss Budget" usedPct={dailyUsed} limitPct={risk.max_daily_loss_pct} />
          <BudgetBar label="Weekly Loss Budget" usedPct={weeklyUsed} limitPct={risk.max_weekly_loss_pct} />
          <BudgetBar label="Drawdown" usedPct={risk.drawdown_pct} limitPct={risk.max_drawdown_pct} />
          <BudgetBar
            label="Portfolio Exposure"
            usedPct={risk.portfolio_exposure_pct}
            limitPct={risk.max_portfolio_exposure_pct}
          />
          {risk.correlated_exposure.map((c) => (
            <BudgetBar
              key={c.symbols.join("+")}
              label={`Correlated Exposure (${c.symbols.join("+")})`}
              usedPct={c.exposure_pct}
              limitPct={risk.max_correlated_exposure_pct}
              detail={`${formatNgn(c.notional)} notional`}
            />
          ))}
          <div className="px-4 py-3">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">Open Positions</span>
            <div className="mt-1 font-mono text-xl font-semibold text-primary">
              {risk.open_positions_count} / {risk.max_open_positions}
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Recent Risk Verdicts">
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          Every signal the risk engine has evaluated, newest first — approved and rejected alike.
        </p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Verdict</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {recentVerdicts.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted">
                    No signals generated yet.
                  </td>
                </tr>
              )}
              {recentVerdicts.map((e) => (
                <tr key={e.signal_id}>
                  <td>{formatDateTime(e.generated_at)}</td>
                  <td>{e.symbol}</td>
                  <td>{e.setup_type}</td>
                  <td>
                    <RiskStatusStamp status={e.risk_status} />
                  </td>
                  <td className="text-muted">{e.risk_verdict_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
