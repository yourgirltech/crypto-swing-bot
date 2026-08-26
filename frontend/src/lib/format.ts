/** Formatting helpers -- keep every number's presentation consistent across pages. */

export function formatNgn(value: number | null | undefined, opts?: { showSign?: boolean }): string {
  if (value === null || value === undefined) return "—";
  const sign = opts?.showSign && value > 0 ? "+" : "";
  return `${sign}₦${value.toLocaleString("en-NG", { maximumFractionDigits: 0 })}`;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatR(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}R`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleString("en-GB", {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

export function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits).replace(/\.?0+$/, "") || "0";
}
