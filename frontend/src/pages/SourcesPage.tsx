import { useState } from "react";
import { AddSourceDialog } from "@/components/AddSourceDialog";
import { SubmitMaterialDialog } from "@/components/SubmitMaterialDialog";
import { Icon } from "@/components/Icon";
import { LoadState } from "@/components/LoadState";
import { StatusPill } from "@/components/StatusPill";
import { useConnectors, useSources } from "@/hooks/useSources";
import { useRegistryStatus } from "@/hooks/useRegistry";
import { nouns, pl } from "@/i18n/pl";
import { formatLastRun } from "@/lib/format";
import { count } from "@/lib/plural";
import { checkedToday, isWaiting, registryRowState, sourceState } from "@/lib/sources";
import { SourceRow } from "@/components/SourceRow";
import { SystemStatus } from "@/components/SystemStatus";

const COLUMNS = "minmax(0, 1fr) 184px 220px 116px 72px 36px";

/** "Monitoring źródeł": what is collected automatically and how it is doing. */
export function SourcesPage() {
  const query = useSources();
  const connectors = useConnectors().data;
  const [adding, setAdding] = useState(false);
  const [reporting, setReporting] = useState(false);
  const sources = query.data ?? [];
  const registry = useRegistryStatus().data;
  const registryRow = registry ? registryRowState(registry) : null;
  const registryOk = registryRow !== null && registryRow.tone !== "high";
  const working =
    sources.filter((s) => ["ok", "running", "new"].includes(sourceState(s))).length +
    (registryOk ? 1 : 0);
  const waiting = sources.filter(isWaiting).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="title">{pl.sources.title}</h1>
          <p className="lead">{pl.sources.lead}</p>
        </div>
        <div className="page-head__actions">
          <button
            type="button"
            className="btn btn--outline btn--md"
            onClick={() => setReporting(true)}
          >
            {pl.sources.report}
          </button>
          <button
            type="button"
            className="btn btn--primary btn--md"
            onClick={() => setAdding(true)}
          >
            <Icon name="plus" size={16} />
            {pl.sources.add}
          </button>
        </div>
      </div>

      <div className="stats stats--3">
        <div className="stat">
          <div className="stat__label">{pl.sources.working}</div>
          <div className="stat__value">{query.data ? count(working, nouns.source) : "–"}</div>
        </div>
        <div className="stat stat--medium">
          <div className="stat__label">{pl.sources.waiting}</div>
          <div className="stat__value">{query.data ? count(waiting, nouns.source) : "–"}</div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.sources.checkedToday}</div>
          <div className="stat__value">
            {query.data ? count(checkedToday(sources), nouns.material) : "–"}
          </div>
        </div>
      </div>

      <SystemStatus />

      {query.isError ? (
        <LoadState error onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <LoadState />
      ) : sources.length === 0 ? (
        <LoadState empty={pl.sources.empty} />
      ) : (
        <div
          className="table"
          style={{ ["--cols" as string]: COLUMNS, ["--row-h" as string]: "76px" }}
        >
          <div className="table__head">
            <span>{pl.sources.columns.source}</span>
            <span>{pl.sources.columns.access}</span>
            <span>{pl.sources.columns.state}</span>
            <span>{pl.sources.columns.last}</span>
            <span className="table__cell--right">{pl.sources.columns.found}</span>
            <span aria-hidden="true" />
          </div>
          {registry && (
            <div className="table__row">
              <span className="table__main">
                <span className="table__title">{pl.sources.registryRow.name}</span>
                <span className="table__sub">{pl.sources.registryRow.what}</span>
              </span>
              <span className="table__cell table__cell--nowrap">
                {pl.sources.registryRow.access}
              </span>
              <span>
                {registryRow && <StatusPill tone={registryRow.tone} label={registryRow.label} />}
              </span>
              <span className="table__cell table__cell--nowrap">
                {formatLastRun(registry.synced_at)}
              </span>
              <span className="table__cell table__cell--strong table__cell--right">
                {pl.sources.registryRow.found(registry.total_active)}
              </span>
              <span />
            </div>
          )}
          {sources.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              connector={connectors?.find((c) => c.collector === source.collector)}
            />
          ))}
        </div>
      )}
      <AddSourceDialog open={adding} onClose={() => setAdding(false)} />
      <SubmitMaterialDialog open={reporting} onClose={() => setReporting(false)} />
    </div>
  );
}
