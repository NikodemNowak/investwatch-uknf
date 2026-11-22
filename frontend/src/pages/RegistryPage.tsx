import { useState } from "react";
import type { FirmKind } from "@/api/types";
import { Icon } from "@/components/Icon";
import { LoadState } from "@/components/LoadState";
import { useDebounced } from "@/hooks/useDebounced";
import { useFirms, useRegistryStatus } from "@/hooks/useRegistry";
import { pl } from "@/i18n/pl";
import { formatInt } from "@/lib/plural";
import { SyncState } from "@/components/SyncState";
import { FirmRow } from "@/components/FirmRow";

const COLUMNS = "minmax(0, 1fr) 232px 120px 184px 104px";
const KINDS: FirmKind[] = [
  "dom_maklerski",
  "bank_maklerski",
  "oddzial_zagraniczny",
  "zagraniczna_bez_oddzialu",
];
const PAGE = 50;

/** "Rejestr KNF": register freshness, counts per register and a searchable firm list. */
export function RegistryPage() {
  const status = useRegistryStatus();
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const search = useDebounced(q.trim());
  const firms = useFirms({ q: search || undefined, limit });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="title">{pl.registry.title}</h1>
          <p className="lead">{pl.registry.lead}</p>
        </div>
        <SyncState status={status.data} />
      </div>

      <div className="stats stats--4">
        {KINDS.map((kind) => (
          <div key={kind} className="stat">
            <div className="stat__label" title={pl.firmKindsPlural[kind]}>
              {pl.firmKindsPlural[kind]}
            </div>
            <div className="stat__value">
              {status.data ? formatInt(status.data.active_per_kind[kind] ?? 0) : "–"}
            </div>
          </div>
        ))}
      </div>
      {status.data && (
        <p className="registry-counts">
          {pl.registry.counts(status.data.total_active, status.data.fictional)}
        </p>
      )}

      <label className="search search--lg">
        <Icon name="search" size={18} />
        <span className="sr-only">{pl.registry.search}</span>
        <input
          type="search"
          placeholder={pl.registry.searchPlaceholder}
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setLimit(PAGE);
          }}
        />
      </label>

      {firms.isError ? (
        <LoadState error onRetry={() => void firms.refetch()} />
      ) : !firms.data ? (
        <LoadState />
      ) : firms.data.items.length === 0 ? (
        <LoadState empty={pl.registry.empty} />
      ) : (
        <div
          className="table"
          style={{ ["--cols" as string]: COLUMNS, ["--row-h" as string]: "72px" }}
        >
          <div className="table__head">
            <span>{pl.registry.columns.firm}</span>
            <span>{pl.registry.columns.kind}</span>
            <span>{pl.registry.columns.country}</span>
            <span>{pl.registry.columns.domain}</span>
            <span className="table__cell--right">{pl.registry.columns.findings}</span>
          </div>
          {firms.data.items.map((row) => (
            <FirmRow key={row.firm.id} row={row} />
          ))}
          {firms.data.total > firms.data.items.length && (
            <div className="table__more">
              <span>{pl.registry.shown(firms.data.items.length, firms.data.total)}</span>
              <button
                type="button"
                className="btn btn--outline btn--md"
                disabled={firms.isFetching}
                onClick={() => setLimit((n) => Math.min(200, n + PAGE))}
              >
                {pl.registry.showMore}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
