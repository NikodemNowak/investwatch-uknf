import { Link, useParams } from "react-router-dom";
import { LoadState } from "@/components/LoadState";
import { useFinding } from "@/hooks/useFinding";
import { pl } from "@/i18n/pl";
import { FindingView } from "@/components/FindingView";
import { BackLink } from "@/components/BackLink";
import { isGone } from "@/lib/polling";

/** "Zgłoszenie": one finding with its problems, the marked screenshot and the decision. */
export function FindingPage() {
  const { id = "" } = useParams();
  const query = useFinding(id);
  if (query.isError) {
    return (
      <div className="page page--detail">
        <BackLink />
        {isGone(query.error) ? (
          <div className="state" role="status">
            <div className="state__title">{pl.finding.deleted}</div>
            <p>{pl.finding.deletedText}</p>
            <Link to="/zgloszenia" className="btn btn--outline btn--md">
              {pl.finding.deletedLink}
            </Link>
          </div>
        ) : (
          <LoadState error onRetry={() => void query.refetch()} />
        )}
      </div>
    );
  }
  if (!query.data) {
    return (
      <div className="page page--detail">
        <BackLink />
        <LoadState />
      </div>
    );
  }
  return <FindingView finding={query.data} />;
}
