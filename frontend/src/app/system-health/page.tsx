import { Panel } from "@/components/Panel";
import { StatTile } from "@/components/StatTile";
import { getSystemHealth } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function StatusDot({ tone }: { tone: "green" | "amber" | "red" }) {
  return <span className={`inline-block h-2 w-2 rounded-full bg-${tone}`} />;
}

function engineTone(status: string): "green" | "amber" | "red" {
  if (status === "running") return "green";
  if (status === "stale") return "amber";
  return "red";
}

export default async function SystemHealthPage() {
  const health = await getSystemHealth();

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Connectivity">
        <div className="grid grid-cols-1 divide-border sm:grid-cols-2 sm:divide-x">
          <div className="flex items-center gap-2 px-4 py-3">
            <StatusDot tone={health.api_ok ? "green" : "red"} />
            <span className="font-mono text-sm text-primary">API: {health.api_ok ? "OK" : "DOWN"}</span>
          </div>
          <div className="flex items-center gap-2 px-4 py-3">
            <StatusDot tone={health.db_ok ? "green" : "red"} />
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
          />
        </div>
      </Panel>

      <Panel title="Paper Trading Engine">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <StatusDot tone={engineTone(health.paper_engine_status)} />
          <span className="font-mono text-sm font-semibold uppercase text-primary">
            {health.paper_engine_status.replace("_", " ")}
          </span>
        </div>
        <div className="px-4 py-3 text-sm text-primary">{health.paper_engine_detail}</div>
        <div className="grid grid-cols-1 sm:grid-cols-3">
          <StatTile
            label="Last Checked In"
            value={health.latest_heartbeat_at ? formatDateTime(health.latest_heartbeat_at) : "Never"}
          />
          <StatTile label="Configured Poll Interval" value={`${health.configured_poll_interval_seconds}s`} />
          <StatTile label="Stale Threshold" value={`${health.heartbeat_stale_threshold_minutes.toFixed(0)} min`} />
        </div>
        <p className="border-t border-border px-4 py-2 text-xs text-muted">
          Recorded at the START of every poll cycle (before any fetch/logic) by{" "}
          <code>paper_trading/engine.py</code> — so even a cycle that later errors still proves the
          process was alive and attempting work at that timestamp. &quot;Stale&quot; means more than{" "}
          {health.heartbeat_stale_threshold_minutes.toFixed(0)} min (2x the configured poll interval)
          have passed since the last check-in without a fresh one; beyond 24h with no heartbeat, this
          reads as &quot;not running&quot; instead.
        </p>
      </Panel>

      <Panel title={`OKX Retry Health — ${health.retry_health.toUpperCase()}`}>
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <StatusDot tone={health.retry_health === "clean" ? "green" : "amber"} />
          <span className="font-mono text-sm text-primary">
            {health.retry_count_recent} retry event{health.retry_count_recent === 1 ? "" : "s"} in the
            last {health.retry_lookback_minutes} min (elevated above {health.retry_elevated_threshold})
          </span>
        </div>
        <p className="border-b border-border px-4 py-2 text-xs text-muted">
          A handful of isolated retries is exactly what the retry-with-backoff logic in{" "}
          <code>data/okx_client.py</code> is FOR — normal, not a problem. &quot;Elevated&quot; means a
          genuinely unusual current burst, not historical noise from days ago.
        </p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Occurred</th>
                <th>Request</th>
                <th>Attempt</th>
                <th>Delay Before Retry</th>
                <th>Exception</th>
              </tr>
            </thead>
            <tbody>
              {health.recent_retry_events.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted">
                    No retry events recorded — every OKX request has succeeded on the first attempt.
                  </td>
                </tr>
              )}
              {health.recent_retry_events.map((ev, i) => (
                <tr key={i}>
                  <td>{formatDateTime(ev.occurred_at)}</td>
                  <td>{ev.request_desc}</td>
                  <td className={ev.attempt_number === ev.max_attempts ? "text-red" : "text-amber"}>
                    {ev.attempt_number} / {ev.max_attempts}
                  </td>
                  <td className="text-muted">{ev.delay_seconds > 0 ? `${ev.delay_seconds.toFixed(0)}s` : "exhausted"}</td>
                  <td className="text-muted">{ev.exception_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
