import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { syncBackend } from "@/api/client";
import type { FindingWithPost, Viewport } from "@/api/types";
import { BackLink } from "@/components/BackLink";
import { Decision } from "@/components/Decision";
import { DemoBadge } from "@/components/DemoBadge";
import { FirmCard } from "@/components/FirmCard";
import { History } from "@/components/History";
import { Occurrences } from "@/components/Occurrences";
import { PdfLink } from "@/components/PdfLink";
import { UnderTheHood } from "@/components/UnderTheHood";
import { Icon } from "@/components/Icon";
import { ScreenshotPanel } from "@/components/ScreenshotPanel";
import { VerdictBanner } from "@/components/VerdictBanner";
import { useRender } from "@/hooks/useRender";
import { pl } from "@/i18n/pl";
import { VIEWPORTS } from "@/lib/enums";
import { displayUrl, formatDayTime, formatScore } from "@/lib/format";
import {
  headlineOf,
  isSupervisedPublisher,
  llmReviewOf,
  modelSignalOf,
  problemsOf,
  plainExplanation,
  proseExplanation,
  summaryOf,
  warningMeasures,
} from "@/lib/problems";
import type { Problem } from "@/lib/problems";

/** Body of the finding page: header, verdict, problems, screenshot, firm and history. */
export function FindingView({ finding }: { finding: FindingWithPost }) {
  const post = finding.post;
  const problems = useMemo(() => problemsOf(finding.rules), [finding.rules]);
  const signal = modelSignalOf(finding);
  const passed = finding.rules.filter((rule) => rule.status === "pass");
  const unknown = finding.rules.filter((rule) => rule.status === "unknown");
  const review = llmReviewOf(finding);
  const supervised = isSupervisedPublisher(finding) && problems.length > 0;
  const fictional = finding.firm?.fictional === true;
  // Same marker as "Sprawdź", so both pages describe a pending model review alike.
  const reviewLabel =
    review === "queued"
      ? pl.check.preliminary
      : review === "unavailable"
        ? pl.llmReview[review]
        : undefined;
  const render = useRender(post?.render_key ? post.id : undefined);
  const backend = syncBackend();
  const shotUrl = (viewport: Viewport) =>
    post && backend ? backend.screenshotUrl(post, viewport) : null;
  const firstLocated = problems.find((p) => p.located && shotUrl(p.located.viewport));
  const [activeRule, setActiveRule] = useState<string | null>(firstLocated?.rule.rule_id ?? null);
  const [viewport, setViewport] = useState<Viewport>(
    firstLocated?.located?.viewport ?? VIEWPORTS.find((v) => shotUrl(v)) ?? "desktop",
  );
  const location = useLocation();

  useEffect(() => {
    if (location.hash === "#zrzut") document.getElementById("zrzut")?.scrollIntoView();
  }, [location.hash]);

  const showOnShot = (problem: Problem) => {
    setActiveRule(problem.rule.rule_id);
    const own = problem.rule.evidence.find((e) => e.bbox && e.viewport === viewport);
    if (!own && problem.located) setViewport(problem.located.viewport);
    document.getElementById("zrzut")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="page page--detail">
      <div className="detail-head">
        <BackLink />
        <div className="detail-head__row">
          <div>
            <h1 className="title">
              {headlineOf(finding)}
              <DemoBadge finding={finding} />
            </h1>
            <p className="detail-head__meta">
              {post ? pl.platformLong[post.platform] : pl.modules[finding.module]}
              {" · "}
              {pl.finding.detected(formatDayTime(finding.created_at))}
              {post && (
                <>
                  {" · "}
                  <a href={post.url} target="_blank" rel="noreferrer noopener">
                    {displayUrl(post.url)}
                  </a>
                </>
              )}
            </p>
            {post?.platform === "youtube" && (
              <p className="detail-head__meta" data-testid="youtube-note">
                {pl.demoBadge.youtubeNote}{" "}
                <a
                  href="https://policies.google.com/privacy"
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {pl.demoBadge.youtubePrivacy}
                </a>
              </p>
            )}
          </div>
          <div className="detail-head__tools">
            <PdfLink
              href={backend?.findingPdfUrl(finding.id) ?? null}
              label={pl.pdf.finding}
              size="lg"
            />
            <Decision finding={finding} />
          </div>
        </div>
      </div>

      <VerdictBanner
        tone={finding.risk_level}
        label={
          fictional
            ? [
                problems.length > 0 ? pl.finding.fictionalNote : pl.finding.firmFictional,
                reviewLabel,
              ]
                .filter(Boolean)
                .join(" · ")
            : supervised
              ? [pl.finding.supervisedNote, reviewLabel].filter(Boolean).join(" · ")
              : reviewLabel
        }
        headline={signal ? signal.title : pl.finding.banner[finding.risk_level](problems.length)}
        text={proseExplanation(plainExplanation(finding)) ?? summaryOf(problems)}
        score={{ value: formatScore(finding.score), label: pl.finding.riskScore }}
      />

      <div className="detail-grid">
        <section aria-labelledby="problems-h" className="stack-12">
          <div className="section-head">
            <h2 id="problems-h" className="h2">
              {pl.finding.problems}
            </h2>
          </div>
          {signal && (
            <article className="problem problem--soft" data-testid="model-signal">
              <span className="num num--soft" aria-hidden="true">
                <Icon name="alert" size={16} color="#ffffff" />
              </span>
              <div>
                <div className="problem__title">{signal.title}</div>
                <div className="problem__text">{signal.text}</div>
                {signal.markers.length > 0 && (
                  <div className="problem__text">
                    {pl.finding.signal.markers}:{" "}
                    {signal.markers.map((marker, index) => (
                      <span key={marker}>
                        {index > 0 && ", "}
                        <q className="signal__marker">{marker}</q>
                      </span>
                    ))}
                  </div>
                )}
                <div className="problem__foot">
                  <span className="problem__law">{pl.finding.signal.foot}</span>
                </div>
              </div>
            </article>
          )}
          {problems.length === 0 && !signal && (
            <div className="passed">{pl.finding.noProblems}</div>
          )}
          {problems.map((problem, index) => {
            const active = problem.rule.rule_id === activeRule;
            const canShow = Boolean(problem.located && shotUrl(problem.located.viewport));
            return (
              <article
                key={problem.rule.rule_id}
                className={[
                  "problem",
                  active ? "problem--active" : "",
                  problem.severe ? "" : "problem--soft",
                ].join(" ")}
              >
                <span className={problem.severe ? "num" : "num num--soft"}>{index + 1}</span>
                <div>
                  <div className="problem__title">{problem.title}</div>
                  <div className="problem__text">{problem.text}</div>
                  <div className="problem__foot">
                    <span className="problem__law">{problem.lawLong}</span>
                    {canShow && (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => showOnShot(problem)}
                      >
                        {pl.finding.showOnShot}
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
          {unknown.length > 0 && (
            <div className="passed">
              <div className="decision">
                {review === "queued" ? (
                  <span className="circle circle--run">
                    <Icon name="spinner" size={18} />
                  </span>
                ) : (
                  <span className="circle circle--skip">
                    <Icon name="dash" size={16} />
                  </span>
                )}
                {review === "queued"
                  ? pl.finding.unknown(unknown.length)
                  : pl.finding.unresolved(unknown.length)}
              </div>
            </div>
          )}
          {passed.length > 0 && (
            <details className="passed">
              <summary>
                <span className="circle circle--done">
                  <Icon name="check" size={16} color="#15803d" />
                </span>
                {pl.finding.passed(passed.length)}
              </summary>
              <ul className="passed__list">
                {passed.map((rule) => (
                  <li key={rule.rule_id}>{rule.name}</li>
                ))}
              </ul>
            </details>
          )}
        </section>

        {post && (
          <ScreenshotPanel
            post={post}
            problems={problems}
            activeRuleId={activeRule}
            viewport={viewport}
            onViewport={setViewport}
            render={render.data}
            shotUrl={shotUrl}
            measures={warningMeasures(finding.rules)}
          />
        )}
      </div>

      <div className="two-cols">
        <FirmCard finding={finding} />
        <History finding={finding} />
      </div>
      <Occurrences finding={finding} />
      <UnderTheHood finding={finding} />
    </div>
  );
}
