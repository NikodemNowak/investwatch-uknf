export type PillTone = "high" | "medium" | "low" | "ok" | "info";

/** Generic status pill with a dot. */
export function StatusPill({ tone, label }: { tone: PillTone; label: string }) {
  return (
    <span className={`pill pill--${tone}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
