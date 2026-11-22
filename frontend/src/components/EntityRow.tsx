import { Link } from "react-router-dom";
import type { EntitySummary } from "@/api/types";
import { EntityTags } from "@/components/EntityTags";
import { RiskPill } from "@/components/RiskPill";
import { pl } from "@/i18n/pl";
import { entityPath } from "@/lib/entities";
import { MODULES } from "@/lib/enums";
import { formatAgo } from "@/lib/format";
import { formatInt } from "@/lib/plural";

/** One row of the aggregator: the entity with counts per module. */
export function EntityRow({ entity }: { entity: EntitySummary }) {
  const [first] = entity.platforms;
  const platforms = first
    ? pl.entities.platforms(pl.platforms[first], entity.platforms.length - 1)
    : "";
  return (
    <div className="table__row table__row--link" data-testid="entity-row">
      <span className="table__main">
        <span className="table__title">
          <Link to={entityPath(entity.key)} className="row-link">
            {entity.name}
          </Link>
        </span>
        <span className="table__sub entity-sub">
          <EntityTags entity={entity} />
          <span className="entity-sub__text">
            {platforms} · {pl.entities.open(entity.open)}
          </span>
        </span>
      </span>
      <span>
        <RiskPill level={entity.highest_risk} />
      </span>
      {MODULES.map((module) => (
        <span
          key={module}
          className={entity.modules[module] ? "num-cell" : "num-cell num-cell--zero"}
          data-testid={`count-${module}`}
        >
          {entity.modules[module] ? formatInt(entity.modules[module]) : "–"}
        </span>
      ))}
      <span className="num-cell">{formatInt(entity.occurrences)}</span>
      <span className="table__cell table__cell--nowrap table__cell--right">
        {formatAgo(entity.latest_at)}
      </span>
    </div>
  );
}
