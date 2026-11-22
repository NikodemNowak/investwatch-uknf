import { Link } from "react-router-dom";
import type { FindingWithPost } from "@/api/types";
import { RiskPill } from "@/components/RiskPill";
import { StatusMenu } from "@/components/StatusMenu";
import { pl } from "@/i18n/pl";
import { formatLocalDate, formatTime } from "@/lib/format";
import { describeFinding, firstSentence, subjectOf } from "@/lib/problems";

/** One finding on an entity's timeline: date first, then the review-list columns. */
export function TimelineRow({ finding }: { finding: FindingWithPost }) {
  return (
    <div className="table__row table__row--link" data-testid="timeline-row">
      <span className="table__cell table__cell--nowrap timeline-date">
        <span className="table__cell--strong">{formatLocalDate(finding.created_at)}</span>
        <span className="timeline-date__time">{formatTime(finding.created_at)}</span>
      </span>
      <span>
        <RiskPill level={finding.risk_level} />
      </span>
      <span className="table__main">
        <span className="table__title">
          <Link to={`/zgloszenia/${finding.id}`} className="row-link">
            {subjectOf(finding)}
          </Link>
          {finding.status !== "new" && (
            <span className={`status-tag status-tag--${finding.status}`}>
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
      <span className="table__action">
        <StatusMenu finding={finding} />
      </span>
    </div>
  );
}
