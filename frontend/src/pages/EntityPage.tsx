import { useState } from "react";
import { useParams } from "react-router-dom";
import { HttpError } from "@/api/http";
import type { EntityDetail, ModuleId } from "@/api/types";
import { BackLink } from "@/components/BackLink";
import { EntityTags } from "@/components/EntityTags";
import { WarningLine } from "@/components/FirmCard";
import { LoadState } from "@/components/LoadState";
import { RiskPill } from "@/components/RiskPill";
import { TimelineRow } from "@/components/TimelineRow";
import { useEntity } from "@/hooks/useEntities";
import { pl } from "@/i18n/pl";
import { MODULES } from "@/lib/enums";
import { formatAgo, formatDate, formatScore } from "@/lib/format";
import { formatInt } from "@/lib/plural";

const COLUMNS = "112px 120px minmax(0, 1fr) 210px 110px 36px";

function EntityView({ entity }: { entity: EntityDetail }) {
  const [module, setModule] = useState<ModuleId | undefined>(undefined);
  const rows = module ? entity.findings.filter((f) => f.module === module) : entity.findings;
  const back = <BackLink to="/podmioty" label={pl.entities.back} />;
  return (
    <div className="page page--detail">
      <div className="detail-head">
        {back}
        <div className="detail-head__row">
          <div>
            <h1 className="title">{entity.name}</h1>
            <p className="detail-head__meta entity-meta">
              <EntityTags entity={entity} />
              <span>
                {entity.firm ? pl.firmKinds[entity.firm.kind] : pl.entities.kind.advertiser}
              </span>
              {entity.firm && entity.knf_register === "knf" && (
                <a href={entity.firm.register_url} target="_blank" rel="noreferrer noopener">
                  {pl.entities.detail.openRegister}
                </a>
              )}
            </p>
          </div>
        </div>
      </div>

      {entity.knf_warning && <WarningLine warning={entity.knf_warning} />}

      <div className="stats stats--4">
        <div className="stat">
          <div className="stat__label">{pl.entities.detail.findings}</div>
          <div className="stat__value">{formatInt(entity.total)}</div>
          <div className="stat__detail">
            {pl.entities.detail.findingsDetail(entity.open, entity.confirmed)}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.detail.risk}</div>
          <div className="stat__value stat__value--pill">
            <RiskPill level={entity.highest_risk} />
          </div>
          <div className="stat__detail">
            {pl.entities.detail.riskDetail(formatScore(entity.max_score))}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.detail.occurrences}</div>
          <div className="stat__value">{formatInt(entity.occurrences)}</div>
          <div className="stat__detail stat__detail--clip">
            {entity.platforms.map((p) => pl.platforms[p]).join(", ")}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.detail.seen}</div>
          <div className="stat__value">{formatAgo(entity.last_seen_at)}</div>
          <div className="stat__detail">
            {pl.entities.detail.seenDetail(formatDate(entity.first_seen_at))}
          </div>
        </div>
      </div>

      <section className="stack-16" aria-labelledby="timeline-h">
        <div className="section-head">
          <h2 className="h2" id="timeline-h">
            {pl.entities.detail.timeline}
          </h2>
          <div role="tablist" className="seg seg--sm">
            {([undefined, ...MODULES] as (ModuleId | undefined)[]).map((id) => (
              <button
                key={id ?? "all"}
                type="button"
                role="tab"
                aria-selected={module === id}
                className="seg__tab seg__tab--count"
                disabled={id !== undefined && entity.modules[id] === 0}
                onClick={() => setModule(id)}
              >
                {id ? pl.moduleTabs[id] : pl.review.all}
                <span className="seg__count">
                  {formatInt(id ? entity.modules[id] : entity.total)}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div
          className="table"
          style={{ ["--cols" as string]: COLUMNS, ["--row-h" as string]: "80px" }}
        >
          <div className="table__head">
            <span>{pl.entities.detail.columns.date}</span>
            <span>{pl.entities.detail.columns.risk}</span>
            <span>{pl.entities.detail.columns.material}</span>
            <span>{pl.entities.detail.columns.kind}</span>
            <span>{pl.entities.detail.columns.source}</span>
            <span />
          </div>
          {rows.map((finding) => (
            <TimelineRow key={finding.id} finding={finding} />
          ))}
        </div>
      </section>
    </div>
  );
}

/** Entity card of the result aggregator: M1/M2/M3 merged, register state and timeline. */
export function EntityPage() {
  const { key = "" } = useParams();
  const query = useEntity(key);
  if (query.data) return <EntityView entity={query.data} />;
  const missing = query.error instanceof HttpError && query.error.status === 404;
  return (
    <div className="page page--detail">
      <BackLink to="/podmioty" label={pl.entities.back} />
      {missing ? (
        <LoadState empty={pl.entities.notFound} />
      ) : query.isError ? (
        <LoadState error onRetry={() => void query.refetch()} />
      ) : (
        <LoadState />
      )}
    </div>
  );
}
