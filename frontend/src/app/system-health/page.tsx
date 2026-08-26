import { Panel } from "@/components/Panel";
import { StatTile } from "@/components/StatTile";
import { getSystemHealth } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-green" : "bg-red"}`} />;
}

export default async function SystemHealthPage() {
  const health = await getSystemHealth();

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Connectivity">
        <div className="grid grid-cols-1 divide-border sm:grid-cols-2 sm:divide-x">
          <div className="flex items-center gap-2 px-4 py-3">
            <StatusDot ok={health.api_ok} />
            <span className="font-mono text-sm text-primary">API: {health.api_ok ? "OK" : "DOWN"}</span>
          </div>
          <div className="flex items-center gap-2 px-4 py-3">
            <StatusDot ok={health.db_ok} />
            <span className="font-mono text-sm text-primary">
              Database: {health.db_ok ? "OK" : "DOWN"}
            </span>
          </div>
        </div>
      </Panel>

      <Panel title="Data Freshness">
        <div className="grid grid-cols-1 sm:grid-cols-2">
          <StatTile
            label="Latest Candle Persisted"
            value={health.latest_candle_time ? formatDateTime(health.latest_candle_time) : "None"}
          />
          <StatTile
            label="Latest Signal Generated"
            value={health.latest_signal_time ? formatDateTime(health.latest_signal_time) : "None"}
            sub="Weak proxy for engine activity — see below"
          />
        </div>
      </Panel>

      <Panel title="Honest Gaps — Not Tracked Yet">
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          This system does not fabricate a status for what it doesn&apos;t actually monitor.
        </p>
        <div className="flex flex-col divide-y divide-border">
          <div className="flex flex-col gap-1 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-amber" />
              <span className="font-mono text-sm text-primary">
                Retry / timeout events: <span className="text-amber">not tracked</span>
              </span>
            </div>
            <p className="text-xs text-muted">
              data/okx_client.py retries transiently in-process (up to 4x with backoff) on a failed
              request, but never writes that event anywhere this API can read — no log table, no log
              file. Adding one would be the fix, not something this page can show today.
            </p>
          </div>
          <div className="flex flex-col gap-1 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-amber" />
              <span className="font-mono text-sm text-primary">
                Paper trading engine liveness: <span className="text-amber">not tracked</span>
              </span>
            </div>
            <p className="text-xs text-muted">
              paper_trading/engine.py is a separate, manually-run process (
              <code>python -m paper_trading.engine</code>) with no heartbeat mechanism — this dashboard
              cannot tell you whether that process is currently running, or when its next poll is
              actually scheduled. It&apos;s configured to poll every {health.configured_poll_interval_seconds}s
              (15 min) if it is running. &quot;Latest signal generated&quot; above is the best available
              proxy, but it&apos;s weak: the engine polls even when no new candle has closed and no setup
              triggers, so a stale timestamp does not necessarily mean the engine is down.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
