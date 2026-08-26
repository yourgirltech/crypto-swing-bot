import { Panel } from "@/components/Panel";
import { PriceChart } from "@/components/charts/PriceChart";
import { getCandles, getOpenPositions } from "@/lib/api";
import { formatDateTime, formatNgn, formatNumber } from "@/lib/format";

export default async function PositionsPage() {
  const positions = await getOpenPositions();
  const chartData = await Promise.all(
    positions.map((p) => getCandles({ symbol: p.symbol, limit: 180 })),
  );

  return (
    <div className="flex flex-col gap-4">
      {positions.map((p, i) => (
        <Panel key={p.signal_id} title={`${p.symbol} — ${p.direction.toUpperCase()} (opened ${formatDateTime(p.entry_time)})`}>
          <p className="border-b border-border px-3 py-2 text-xs text-muted">
            Last-polled candles, not a live feed — see Milestone 4&apos;s polling-vs-streaming decision.
          </p>
          {chartData[i].length === 0 ? (
            <p className="p-4 text-sm text-muted">No candles persisted yet for {p.symbol}.</p>
          ) : (
            <PriceChart
              candles={chartData[i]}
              markers={{
                entry_price: p.entry_fill_price ?? p.entry_price,
                stop_price: p.stop_price,
                target_price: p.target_price,
                direction: p.direction,
              }}
            />
          )}
        </Panel>
      ))}

      <Panel title={`Open Positions (${positions.length})`}>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Dir</th>
                <th>Entry Fill</th>
                <th>Stop</th>
                <th>Target</th>
                <th>Size</th>
                <th>Risk</th>
                <th>Entry Time</th>
                <th>Regime</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-muted">
                    No open positions right now.
                  </td>
                </tr>
              )}
              {positions.map((p) => (
                <tr key={p.signal_id}>
                  <td>{p.symbol}</td>
                  <td className={p.direction === "long" ? "text-green" : "text-red"}>
                    {p.direction.toUpperCase()}
                  </td>
                  <td>{p.entry_fill_price?.toFixed(2) ?? "—"}</td>
                  <td className="text-red">{p.stop_price.toFixed(2)}</td>
                  <td className="text-green">{p.target_price.toFixed(2)}</td>
                  <td>{formatNumber(p.position_size, 6)}</td>
                  <td>{formatNgn(p.risk_amount)}</td>
                  <td>{formatDateTime(p.entry_time)}</td>
                  <td className="text-muted">{p.regime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
