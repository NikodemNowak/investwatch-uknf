import type { FirmSummary } from "@/api/types";
import { pl } from "@/i18n/pl";
import { formatCountry } from "@/lib/format";
import { formatInt } from "@/lib/plural";

/** One firm of the KNF register (or a fictional demo firm, marked as such). */
export function FirmRow({ row }: { row: FirmSummary }) {
  const { firm } = row;
  const aliases = firm.aliases.filter((a) => a !== firm.name);
  return (
    <div className="table__row">
      <span className="table__main">
        <span className="table__title">{firm.name}</span>
        <span className="table__sub">
          {row.source !== "knf" && (
            <span className="firm-fictional" title={pl.registry.fictionalHint}>
              {pl.registry.fictional}
            </span>
          )}
          {aliases.length ? pl.registry.alias(aliases) : pl.registry.noAlias}
        </span>
      </span>
      <span className="table__cell table__cell--nowrap">{pl.firmKinds[firm.kind]}</span>
      <span className="table__cell table__cell--nowrap">
        {firm.country ? formatCountry(firm.country) : pl.common.dash}
      </span>
      <span className="table__cell table__cell--nowrap" title={firm.domains.join(", ")}>
        {firm.domains[0] ?? pl.common.dash}
      </span>
      <span
        className={`table__cell table__cell--right table__cell--strong ${row.findings ? "findings-count--hit" : "findings-count--zero"}`}
      >
        {formatInt(row.findings)}
      </span>
    </div>
  );
}
