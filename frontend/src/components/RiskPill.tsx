import type { RiskLevel } from "@/api/types";
import { pl } from "@/i18n/pl";

/** Risk level as a coloured pill with a dot ("Wysokie"). */
export function RiskPill({ level }: { level: RiskLevel }) {
  return (
    <span className={`pill pill--${level}`}>
      <span className="dot" />
      {pl.risk[level]}
    </span>
  );
}
