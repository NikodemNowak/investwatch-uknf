import { Link } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { Facts } from "@/components/Facts";
import { ProgressCard } from "@/components/ProgressCard";
import { VerdictBanner } from "@/components/VerdictBanner";
import type { VerdictTone } from "@/components/VerdictBanner";
import { useNow } from "@/hooks/useNow";
import { pl } from "@/i18n/pl";
import { primaryFinding, verdictOf } from "@/lib/verdict";
import type { CheckRun } from "@/state/checkContext";

/** Progress, verdict, facts and problems of the running check. */
export function CheckResult({ run }: { run: CheckRun }) {
  const { progress, findings, post } = run;
  const now = useNow(!progress.finished);
  const elapsed = (run.finishedAt ?? now) - run.startedAt;
  const verdict = verdictOf(findings, progress.phase);
  const primary = primaryFinding(findings);
  const analyzed = progress.phase !== "pending" && progress.phase !== "failed";

  let tone: VerdictTone = "info";
  let label = pl.check.pendingTitle;
  let headline = pl.check.pendingHeadline;
  let text = pl.check.pendingText;
  if (progress.phase === "failed") {
    tone = "neutral";
    label = pl.check.failedTitle;
    headline = pl.check.failedHeadline;
    const status = /fetch_status=(\w+)/.exec(run.error ?? "")?.[1];
    text =
      status === "blocked" || status === "error" || status === "no_text"
        ? pl.check.failedReasons[status]
        : (run.error ?? pl.check.failedReasons.other);
  } else if (progress.phase === "duplicate") {
    tone = "neutral";
    label = pl.check.final;
    headline = pl.check.duplicateHeadline;
    text = pl.check.duplicateText;
  } else if (analyzed) {
    tone = verdict.risk ?? "low";
    label = progress.phase === "preliminary" ? pl.check.preliminary : pl.check.final;
    headline = verdict.headline;
    text = verdict.text;
  }

  return (
    <section className="check-grid" aria-label={pl.check.progress}>
      <ProgressCard progress={progress} elapsedMs={elapsed} />
      <div className="result">
        <VerdictBanner tone={tone} label={label} headline={headline} text={text} />
        {post && <Facts post={post} findings={findings} analyzed={analyzed} />}
        {analyzed && (
          <div className="issues">
            {verdict.problems.map((problem) => (
              <div key={problem.rule.rule_id + problem.title} className="issue">
                <span className="circle circle--bad">
                  <Icon name="cross" size={14} color="#b91c1c" />
                </span>
                <div>
                  <div className="issue__title">{problem.title}</div>
                  <div className="issue__text">{problem.short}</div>
                </div>
                <span className="issue__law">{problem.lawShort}</span>
              </div>
            ))}
            {verdict.signal && (
              <div className="issue issue--signal" data-testid="model-signal">
                <span className="circle circle--warn">
                  <Icon name="alert" size={16} color="#b45309" />
                </span>
                <div>
                  <div className="issue__title">{verdict.signal.title}</div>
                  <div className="issue__text">{verdict.signal.text}</div>
                </div>
              </div>
            )}
            {verdict.problems.length === 0 &&
              !verdict.signal &&
              progress.phase !== "preliminary" && (
                <div className="issue issue--empty">
                  <span className="circle circle--done">
                    <Icon name="check" size={16} color="#15803d" />
                  </span>
                  <div>{pl.check.noProblems}</div>
                </div>
              )}
            {progress.phase === "preliminary" && (
              <div className="issue issue--pending">
                <span className="circle">
                  <Icon name="spinner" size={18} />
                </span>
                <div>
                  {verdict.pending.length
                    ? pl.check.stillChecking(verdict.pending.join(", "))
                    : pl.check.steps.llm.run}
                </div>
              </div>
            )}
          </div>
        )}
        {primary && (
          <div className="actions">
            <Link to={`/zgloszenia/${primary.id}`} className="btn btn--dark">
              {pl.check.openFinding}
            </Link>
            {post && Object.keys(post.screenshot_keys).length > 0 && (
              <Link to={`/zgloszenia/${primary.id}#zrzut`} className="btn btn--outline">
                {pl.check.seeShots}
              </Link>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
