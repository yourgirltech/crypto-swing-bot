import { Panel } from "@/components/Panel";
import { OutcomeStamp } from "@/components/VerdictStamp";
import { listJournalEntries } from "@/lib/api";
import { formatDateTime, formatNgn, formatR } from "@/lib/format";

/**
 * "Orders" here means executed paper-trade fills -- this system has no
 * separate live-exchange order concept yet (that's Milestone 12); every
 * fill a paper trade produces IS the order record for now. Filtered from
 * the journal to entries with an actual paper_trade_id (risk engine AND
 * human both approved), not every signal.
 */
export default async function OrdersPage() {
  const entries = await listJournalEntries({ limit: 200 });
  const orders = entries.filter((e) => e.paper_trade_id !== null);

  return (
    <div className="flex flex-col gap-4">
      <Panel title={`Order Fills (${orders.length})`}>
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          Simulated paper-trading fills, not live exchange orders — this system runs paper-only until Milestone 12.
        </p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Dir</th>
                <th>Entry Fill</th>
                <th>Entry Fee</th>
                <th>Exit Fill</th>
                <th>Exit Fee</th>
                <th>Status</th>
                <th>Outcome</th>
                <th>R (real.)</th>
                <th className="text-right">P&L</th>
                <th>Entry Time</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 && (
                <tr>
                  <td colSpan={11} className="py-6 text-center text-muted">
                    No order fills yet.
                  </td>
                </tr>
              )}
              {orders.map((o) => (
                <tr key={o.signal_id}>
                  <td>{o.symbol}</td>
                  <td className={o.direction === "long" ? "text-green" : "text-red"}>
                    {o.direction.toUpperCase()}
                  </td>
                  <td>{o.entry_fill_price?.toFixed(2) ?? "—"}</td>
                  <td className="text-muted">{formatNgn(o.entry_fee)}</td>
                  <td>{o.exit_fill_price?.toFixed(2) ?? "—"}</td>
                  <td className="text-muted">{formatNgn(o.exit_fee)}</td>
                  <td className="uppercase text-muted">{o.paper_trade_status}</td>
                  <td>
                    <OutcomeStamp outcome={o.outcome} />
                  </td>
                  <td className={o.r_multiple_realistic == null ? "text-muted" : o.r_multiple_realistic >= 0 ? "text-green" : "text-red"}>
                    {formatR(o.r_multiple_realistic)}
                  </td>
                  <td
                    className={`text-right ${
                      o.pnl_ngn == null ? "text-muted" : o.pnl_ngn >= 0 ? "text-green" : "text-red"
                    }`}
                  >
                    {formatNgn(o.pnl_ngn, { showSign: true })}
                  </td>
                  <td>{formatDateTime(o.entry_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
