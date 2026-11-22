import { Link } from "react-router-dom";
import type { FindingWithPost } from "@/api/types";
import { DemoBadge } from "@/components/DemoBadge";
import { RiskPill } from "@/components/RiskPill";
import { StatusMenu } from "@/components/StatusMenu";
import { pl } from "@/i18n/pl";
import { formatAgo } from "@/lib/format";
import { describeFinding, firstSentence, subjectOf } from "@/lib/problems";

/** One row of the review list: the title links to the finding, "⋯" changes the status. */
export function ReviewRow({ finding }: { finding: FindingWithPost }) {
  return (
    <div className="table__row table__row--link" data-testid="review-row">
      <span>
        <RiskPill level={finding.risk_level} />
      </span>
      <span className="table__main">
        <span className="table__title table__title--tags">
          <Link to={`/zgloszenia/${finding.id}`} className="row-link">
            {subjectOf(finding)}
          </Link>
          <DemoBadge finding={finding} compact />
          {finding.duplicates > 0 && (
            <span className="occ-badge" data-testid="occurrences">
              {pl.review.occurrences(finding.duplicates + 1)}
            </span>
          )}
          {finding.status !== "new" && (
            <span className={`status-tag status-tag--${finding.status}`} data-testid="status-tag">
              {pl.review.statusTag[finding.status]}
            </span>
          )}
        </span>
        <span className="table__sub" title={describeFinding(finding)}>
          {firstSentence(describeFinding(finding))}
        </span>
      </span>
      <span className="table__cell table__cell--nowrap">{pl.modules[finding.module]}</span>
      <span className="table__cell table__cell--nowrap">
        {finding.post ? pl.platforms[finding.post.platform] : "–"}
      </span>
      <span className="table__cell table__cell--nowrap table__cell--right">
        {formatAgo(finding.created_at)}
      </span>
      <span className="table__action">
        <StatusMenu finding={finding} />
      </span>
    </div>
  );
}
