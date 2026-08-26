import { Panel } from "@/components/Panel";
import { HumanDecisionStamp, RiskStatusStamp } from "@/components/VerdictStamp";
import { listJournalEntries } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default async function AiInsightsPage() {
  const entries = await listJournalEntries({ limit: 1 });
  const latest = entries[0];

  return (
    <div className="flex flex-col gap-4">
      <Panel title="AI Insights — Full Trade Review">
        <p className="border-b border-border px-3 py-2 text-xs text-muted">
          Surfaces reporting/plain_language_summary.py&apos;s full trade review — the exact text a
          human saw at the CLI approval step. This is a historical record, never a live decision.
        </p>

        {!latest && <p className="p-4 text-sm text-muted">No signals have been generated yet.</p>}

        {latest && (
          <div className="flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-sm text-primary">
                {latest.symbol} — {latest.setup_type}
              </span>
              <RiskStatusStamp status={latest.risk_status} />
              <HumanDecisionStamp decision={latest.human_decision} />
              <span className="font-mono text-xs text-muted">
                Generated {formatDateTime(latest.generated_at)} — historical, not a pending decision.
              </span>
            </div>

            {latest.approval_summary ? (
              <pre className="whitespace-pre-wrap border border-border bg-surface p-4 font-mono text-xs leading-relaxed text-primary">
                {latest.approval_summary}
              </pre>
            ) : (
              <div className="border border-border bg-surface p-4 text-sm">
                <p className="mb-3 text-muted">
                  No stored full trade review exists for this signal. That text is only generated (and
                  saved) when the risk engine approves a proposal <em>and</em> a human is then asked to
                  approve or decline it via the paper trading engine —{" "}
                  {latest.risk_status === "rejected"
                    ? "this signal was rejected by the risk engine before a human was ever asked."
                    : latest.human_decision === null
                      ? "this signal was approved by the risk engine, but no human decision has been recorded for it yet."
                      : "this signal was declined by a human."}
                </p>
                <p className="mb-1 font-mono text-[0.7rem] uppercase tracking-wider text-muted">
                  What is on record for this signal:
                </p>
                <ul className="list-inside list-disc font-mono text-xs text-primary">
                  <li>
                    Trend {latest.trend}, regime {latest.regime}, RSI {latest.rsi}
                  </li>
                  <li>
                    Entry {latest.entry_price} / Stop {latest.stop_price} / Target {latest.target_price} (
                    {latest.reward_risk_ratio.toFixed(1)}:1)
                  </li>
                  <li>
                    Risk verdict: {latest.risk_status}
                    {latest.risk_verdict_reason ? ` — ${latest.risk_verdict_reason}` : ""}
                  </li>
                  <li className="text-muted">{latest.notes}</li>
                </ul>
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
