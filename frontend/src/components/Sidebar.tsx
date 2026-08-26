import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/positions", label: "Positions" },
  { href: "/orders", label: "Orders" },
  { href: "/strategies", label: "Strategies" },
  { href: "/backtesting", label: "Backtesting" },
];

export function Sidebar() {
  return (
    <nav className="flex w-44 shrink-0 flex-col border-r border-border bg-surface">
      <div className="border-b border-border px-4 py-3">
        <span className="font-mono text-xs font-semibold tracking-wider text-primary">
          SWING/BOT
        </span>
      </div>
      <ul className="flex flex-col py-2">
        {NAV_ITEMS.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="block px-4 py-2 text-sm text-muted hover:bg-surface-hover hover:text-primary"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
