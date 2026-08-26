/** Numbers are the visual hierarchy here -- large mono figure, small muted label, optional semantic tone. */
export function StatTile({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: "green" | "red" | "amber" | "neutral";
  sub?: string;
}) {
  const toneClass =
    tone === "green" ? "text-green" : tone === "red" ? "text-red" : tone === "amber" ? "text-amber" : "text-primary";

  return (
    <div className="flex flex-col gap-1 border-r border-border px-4 py-3 last:border-r-0">
      <span className="font-mono text-[0.65rem] uppercase tracking-wider text-muted">{label}</span>
      <span className={`font-mono text-xl font-semibold ${toneClass}`}>{value}</span>
      {sub && <span className="text-[0.7rem] text-muted">{sub}</span>}
    </div>
  );
}
