/**
 * Signature element for this dashboard: every risk-engine verdict and
 * human decision renders as a literal bracketed terminal stamp, tying the
 * visual identity to the actual mechanic this system is built around --
 * the risk engine's veto authority over every trade. Monospace, thin
 * colored border, no fill -- restrained, not decorative.
 */

type StampTone = "green" | "red" | "amber" | "muted";

const TONE_CLASSES: Record<StampTone, string> = {
  green: "border-green text-green",
  red: "border-red text-red",
  amber: "border-amber text-amber",
  muted: "border-border text-muted",
};

export function Stamp({ label, tone }: { label: string; tone: StampTone }) {
  return (
    <span
      className={`inline-block rounded-[3px] border px-2 py-0.5 font-mono text-[0.7rem] font-medium tracking-wide ${TONE_CLASSES[tone]}`}
    >
      [ {label} ]
    </span>
  );
}

export function RiskStatusStamp({ status }: { status: "pending" | "approved" | "rejected" }) {
  if (status === "approved") return <Stamp label="APPROVED" tone="green" />;
  if (status === "rejected") return <Stamp label="REJECTED" tone="red" />;
  return <Stamp label="PENDING" tone="amber" />;
}

export function HumanDecisionStamp({ decision }: { decision: "approved" | "declined" | null }) {
  if (decision === "approved") return <Stamp label="APPROVED" tone="green" />;
  if (decision === "declined") return <Stamp label="DECLINED" tone="red" />;
  return <Stamp label="AWAITING" tone="muted" />;
}

export function OutcomeStamp({ outcome }: { outcome: "win" | "loss" | null }) {
  if (outcome === "win") return <Stamp label="WIN" tone="green" />;
  if (outcome === "loss") return <Stamp label="LOSS" tone="red" />;
  return <Stamp label="OPEN" tone="amber" />;
}
