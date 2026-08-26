/** Visualizes "X of Y% used" against a configured limit -- the core "is the guardrail working" signal. */
export function BudgetBar({
  label,
  usedPct,
  limitPct,
  detail,
}: {
  label: string;
  usedPct: number;
  limitPct: number;
  detail?: string;
}) {
  const ratio = limitPct > 0 ? Math.min(100, Math.max(0, (usedPct / limitPct) * 100)) : 0;
  const tone = ratio >= 90 ? "bg-red" : ratio >= 66 ? "bg-amber" : "bg-green";

  return (
    <div className="flex flex-col gap-1.5 px-4 py-3">
      <div className="flex items-baseline justify-between font-mono text-xs">
        <span className="uppercase tracking-wider text-muted">{label}</span>
        <span className="text-primary">
          {usedPct.toFixed(2)}% of {limitPct.toFixed(2)}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-border">
        <div className={`h-full ${tone}`} style={{ width: `${ratio}%` }} />
      </div>
      {detail && <span className="text-[0.7rem] text-muted">{detail}</span>}
    </div>
  );
}
