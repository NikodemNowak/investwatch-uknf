import type { EntitySummary } from "@/api/types";
import { pl } from "@/i18n/pl";

/** Register state and warning-list flag of an entity, as small tags. */
export function EntityTags({ entity }: { entity: EntitySummary }) {
  return (
    <span className="entity-tags">
      <span
        className={`tag tag--${entity.knf_register}`}
        data-testid="register-tag"
        title={pl.entities.registerHint[entity.knf_register]}
      >
        {pl.entities.register[entity.knf_register]}
      </span>
      {entity.knf_warning && (
        <span className="tag tag--warning" data-testid="warning-tag">
          {pl.entities.warning}
        </span>
      )}
    </span>
  );
}
