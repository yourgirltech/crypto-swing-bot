import { Panel } from "@/components/Panel";
import { HumanDecisionStamp, OutcomeStamp, RiskStatusStamp } from "@/components/VerdictStamp";
import { listJournalEntries } from "@/lib/api";
import { formatDateTime, formatNgn } from "@/lib/format";

type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>;

function str(v: string | string[] | undefined): string | undefined {
  const s = Array.isArray(v) ? v[0] : v;
  return s ? s : undefined;
}

const selectClass =
  "border border-border bg-surface px-2 py-1 font-mono text-xs text-primary focus:outline-none focus:border-primary";

export default async function JournalPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const symbol = str(sp.symbol);
  const riskStatus = str(sp.risk_status);
  const humanDecision = str(sp.human_decision);
  const outcome = str(sp.outcome);

  const entries = await listJournalEntries({
    symbol,
    risk_status: riskStatus,
    human_decision: humanDecision,
    outcome,
    limit: 200,
  });

  const anyFilterActive = Boolean(symbol || riskStatus || humanDecision || outcome);
  const closedCount = entries.filter((e) => e.paper_trade_status === "closed").length;

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Filter Journal">
        <form method="get" className="flex flex-wrap items-end gap-4 px-3 py-3">
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">Symbol</span>
            <select name="symbol" defaultValue={symbol ?? ""} className={selectClass}>
              <option value="">All</option>
              <option value="BTCUSDT">BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">Risk Verdict</span>
            <select name="risk_status" defaultValue={riskStatus ?? ""} className={selectClass}>
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">Human Decision</span>
            <select name="human_decision" defaultValue={humanDecision ?? ""} className={selectClass}>
              <option value="">All</option>
              <option value="approved">Approved</option>
              <option value="declined">Declined</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">Outcome</span>
            <select name="outcome" defaultValue={outcome ?? ""} className={selectClass}>
              <option value="">All</option>
              <option value="win">Win</option>
              <option value="loss">Loss</option>
            </select>
          </label>
          <button
            type="submit"
            className="border border-border bg-surface-hover px-3 py-1 font-mono text-xs text-primary hover:border-primary"
          >
            Apply
          </button>
          {anyFilterActive && (
            <a href="/journal" className="font-mono text-xs text-muted underline hover:text-primary">
              Clear filters
            </a>
          )}
        </form>
      </Panel>

      <Panel title={`Journal Entries (${entries.length}${anyFilterActive ? " matching filters" : ""})`}>
        {closedCount === 0 && (
          <p className="border-b border-border px-3 py-2 text-xs text-muted">
            {entries.length === 0
              ? "No signals match these filters."
              : `${entries.length} signal${entries.length === 1 ? "" : "s"} shown, but none has a closed trade yet — most of this history is still proposals awaiting or past a decision, not realized outcomes.`}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Generated</th>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Dir</th>
                <th>Regime</th>
                <th>Entry</th>
                <th>Stop</th>
                <th>Target</th>
                <th>Risk Verdict</th>
                <th>Human</th>
                <th>Outcome</th>
                <th className="text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && (
                <tr>
                  <td colSpan={12} className="py-6 text-center text-muted">
                    Nothing here.
                  </td>
                </tr>
              )}
              {entries.map((e) => (
                <tr key={e.signal_id}>
                  <td>{formatDateTime(e.generated_at)}</td>
                  <td>{e.symbol}</td>
                  <td>{e.setup_type}</td>
                  <td className={e.direction === "long" ? "text-green" : "text-red"}>
                    {e.direction.toUpperCase()}
                  </td>
                  <td className="text-muted">{e.regime}</td>
                  <td>{e.entry_price.toFixed(2)}</td>
                  <td className="text-red">{e.stop_price.toFixed(2)}</td>
                  <td className="text-green">{e.target_price.toFixed(2)}</td>
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
                    {e.pnl_ngn == null ? "—" : formatNgn(e.pnl_ngn, { showSign: true })}
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
