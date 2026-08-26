import { getAccountSummary } from "@/lib/api";
import { formatNgn, formatPct } from "@/lib/format";

function pnlTone(pct: number): string {
  if (pct > 0) return "text-green";
  if (pct < 0) return "text-red";
  return "text-muted";
}

/** Persistent top bar -- account equity, open positions, daily/weekly P&L, risk budget used. */
export async function TickerBar() {
  const account = await getAccountSummary();
  const dailyBudgetUsedPct = Math.min(
    100,
    (Math.max(0, -account.daily_pnl_pct) / account.max_daily_loss_pct) * 100,
  );

  return (
    <div className="flex items-center gap-6 border-b border-border bg-surface px-4 py-2 font-mono text-xs">
      <TickerItem label="EQUITY" value={formatNgn(account.account_equity)} />
      <TickerItem
        label="POSITIONS"
        value={`${account.open_positions_count}/${account.max_open_positions}`}
      />
      <TickerItem
        label="DAILY P&L"
        value={formatPct(account.daily_pnl_pct, 2)}
        className={pnlTone(account.daily_pnl_pct)}
      />
      <TickerItem
        label="WEEKLY P&L"
        value={formatPct(account.weekly_pnl_pct, 2)}
        className={pnlTone(account.weekly_pnl_pct)}
      />
      <TickerItem
        label="DAILY LOSS BUDGET"
        value={`${dailyBudgetUsedPct.toFixed(0)}% of ${account.max_daily_loss_pct.toFixed(0)}%`}
        className={dailyBudgetUsedPct > 66 ? "text-amber" : undefined}
      />
    </div>
  );
}

function TickerItem({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-muted">{label}</span>
      <span className={className ?? "text-primary"}>{value}</span>
    </div>
  );
}
