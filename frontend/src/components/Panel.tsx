import type { ReactNode } from "react";

export function Panel({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel flex flex-col ${className ?? ""}`}>
      {title && (
        <header className="border-b border-border px-3 py-2">
          <h2 className="font-mono text-[0.7rem] font-semibold uppercase tracking-wider text-muted">
            {title}
          </h2>
        </header>
      )}
      <div className="flex-1">{children}</div>
    </section>
  );
}
