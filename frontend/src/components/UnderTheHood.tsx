import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { FindingWithPost, UnderTheHood as Hood } from "@/api/types";
import { useFindingTrace } from "@/hooks/useFindingTrace";
import { pl } from "@/i18n/pl";
import { displayUrl, formatDayTime, formatNumber, formatSeconds, formatWhen } from "@/lib/format";
import { formatBytes, shortHash, shortId, sourceName, timingSteps } from "@/lib/hood";

const t = pl.hood;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

/** A hash shown short, full value in the title, with a copy button. */
function Hash({ value }: { value: string | null | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="hood__muted">{t.none}</span>;
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <span className="hood__hash">
      <code title={value}>{shortHash(value, 16)}</code>
      <button type="button" className="link-button hood__copy" onClick={copy}>
        {copied ? t.copied : t.copy}
      </button>
    </span>
  );
}

function FetchSection({ hood }: { hood: Hood }) {
  const f = hood.fetch;
  const job = hood.collect_job;
  const crawler = f?.access_mode === "crawler";
  return (
    <section className="hood__card">
      <h3 className="hood__h">{t.sections.fetch}</h3>
      <dl className="hood__dl">
        <Row label={t.rows.source}>{sourceName(hood, t.manual, t.collectors)}</Row>
        {hood.source && (
          <Row label={t.rows.schedule}>
            <code>{hood.source.cron}</code>
            {hood.source.next_run_at && (
              <span className="hood__muted">
                {" · "}
                {t.rows.nextRun.toLowerCase()} {formatWhen(hood.source.next_run_at)}
              </span>
            )}
          </Row>
        )}
        {job && (
          <Row label={t.rows.job}>
            <code>{job.task.replace("investwatch.", "")}</code>
            <div className="hood__muted">{t.task(job.queue, shortId(job.task_id), job.worker)}</div>
          </Row>
        )}
        <Row label={t.rows.access}>
          {f?.access_mode ? (t.access[f.access_mode] ?? f.access_mode) : t.none}
        </Row>
        {f?.legal_basis && <Row label={t.rows.basis}>{f.legal_basis}</Row>}
        {crawler && (
          <>
            <Row label={t.rows.userAgent}>
              <code className="hood__wrap">{f?.user_agent ?? t.none}</code>
            </Row>
            <Row label={t.rows.proxy}>{f?.proxy ? <code>{f.proxy}</code> : t.direct}</Row>
            <Row label={t.rows.robots}>
              {f?.robots ? (t.robots[f.robots] ?? f.robots) : t.none}
              {f?.crawl_delay_s != null && (
                <span className="hood__muted">
                  {" · "}
                  {t.crawlDelay(formatNumber(f.crawl_delay_s))}
                </span>
              )}
            </Row>
            <Row label={t.rows.http}>
              {t.httpLine(
                f?.http_status,
                f?.elapsed_ms != null ? formatNumber(Math.round(f.elapsed_ms)) : null,
              ) || t.none}
            </Row>
            <Row label={t.rows.render}>
              {f?.render === "ok"
                ? t.renderOk(f.render_ms != null ? formatSeconds(f.render_ms) : null)
                : (f?.render ?? t.renderOff)}
            </Row>
          </>
        )}
        {f?.fetched_at && <Row label={t.rows.fetchedAt}>{formatDayTime(f.fetched_at)}</Row>}
      </dl>
    </section>
  );
}

function StorageSection({ hood }: { hood: Hood }) {
  return (
    <section className="hood__card hood__card--wide">
      <h3 className="hood__h">{t.sections.storage}</h3>
      <table className="hood__table">
        <thead>
          <tr>
            <th>{t.columns.object}</th>
            <th>{t.columns.key}</th>
            <th className="hood__num">{t.columns.size}</th>
            <th>{t.columns.sha}</th>
          </tr>
        </thead>
        <tbody>
          {hood.objects.map((o) => (
            <tr key={o.key}>
              <td>
                {t.objectKinds[o.kind] ?? o.kind}
                {o.kind === "screenshot" &&
                  ` (${pl.viewports[o.label as keyof typeof pl.viewports] ?? o.label})`}
              </td>
              <td>
                <code className="hood__wrap">
                  {o.bucket}/{o.key}
                </code>
              </td>
              <td className="hood__num">{formatBytes(o.bytes)}</td>
              <td>{o.sha256 ? <Hash value={o.sha256} /> : t.missingObject}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="hood__dl hood__dl--after">
        <Row label={t.rows.textHash}>
          <Hash value={hood.content_hash} />
        </Row>
        {hood.render_hash && (
          <Row label={t.rows.layoutHash}>
            <Hash value={hood.render_hash} />
          </Row>
        )}
      </dl>
    </section>
  );
}

function AnalysisSection({ hood }: { hood: Hood }) {
  const trace = hood.trace;
  const llm = trace?.llm;
  const m = hood.model;
  return (
    <section className="hood__card">
      <h3 className="hood__h">{t.sections.analysis}</h3>
      <dl className="hood__dl">
        <Row label={t.rows.tokens}>
          {hood.tokens != null ? formatNumber(hood.tokens) : t.none}
          {trace && <span className="hood__muted"> · {t.chars(formatNumber(trace.chars))}</span>}
        </Row>
        <Row label={t.rows.embedding}>{t.embedding(trace?.embedding_dim, trace?.embed_model)}</Row>
        {trace?.lang && <Row label={t.rows.lang}>{trace.lang}</Row>}
        <Row label={t.rows.rules}>
          <code>{m.rules_version ?? trace?.rules_version ?? t.none}</code>
        </Row>
        <Row label={t.rows.classifier}>
          {m.classifier ? t.classifierLine(m.classifier, m.classifier_variant) : t.noClassifier}
          {hood.classifier_note && <div className="hood__muted">{hood.classifier_note}</div>}
        </Row>
        {trace?.task && (
          <Row label={t.rows.analyze}>
            {t.task(trace.task.queue, shortId(trace.task.task_id), trace.task.worker)}
          </Row>
        )}
        <Row label={t.rows.llm}>
          {llm
            ? t.llmLine(
                llm.model,
                llm.prompt_tokens,
                llm.output_tokens,
                llm.ms != null ? formatSeconds(llm.ms) : null,
              )
            : t.noLlm}
          {llm?.error && <div className="hood__muted">{llm.error}</div>}
        </Row>
        {llm?.task && (
          <Row label={t.rows.llmTask}>
            {t.task(llm.task.queue, shortId(llm.task.task_id), llm.task.worker)}
          </Row>
        )}
      </dl>
    </section>
  );
}

function TimingsSection({ hood }: { hood: Hood }) {
  const { steps, total } = timingSteps(hood.trace?.timings_ms);
  return (
    <section className="hood__card">
      <h3 className="hood__h">{t.sections.timings}</h3>
      {steps.length === 0 ? (
        <p className="hood__muted">{t.noTimings}</p>
      ) : (
        <>
          <ul className="hood__steps">
            {steps.map((step) => (
              <li key={step.key}>
                <span>{t.steps[step.key] ?? step.key}</span>
                <span className="hood__bar" aria-hidden="true">
                  <span style={{ width: `${Math.max(2, step.share * 100)}%` }} />
                </span>
                <span className="hood__num">{formatNumber(Math.round(step.ms))} ms</span>
              </li>
            ))}
          </ul>
          <p className="hood__muted">{t.total(formatNumber(Math.round(total)))}</p>
        </>
      )}
      <h3 className="hood__h hood__h--gap">{t.sections.similar}</h3>
      {!hood.similar_available ? (
        <p className="hood__muted">{t.similarOff}</p>
      ) : hood.similar.length === 0 ? (
        <p className="hood__muted">{t.noSimilar}</p>
      ) : (
        <ul className="hood__similar">
          {hood.similar.map((s) => (
            <li key={s.post_id}>
              {s.finding_id ? (
                <Link to={`/zgloszenia/${s.finding_id}`}>{displayUrl(s.url)}</Link>
              ) : (
                <span>{displayUrl(s.url)}</span>
              )}
              <span className="hood__muted">
                {" · "}
                {t.similarity(formatNumber(Math.round(s.similarity * 100)))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Collapsible "Pod maską": the processing trace of the finding's material, for the jury. */
export function UnderTheHood({ finding }: { finding: FindingWithPost }) {
  // Loaded with the page: the summary line (source, fetch time, access mode) is visible closed.
  const query = useFindingTrace(finding.id, true);
  const hood = query.data;
  const post = finding.post;
  const collector = post?.collector ?? "";
  const mode = hood?.fetch?.access_mode;
  const chip = hood
    ? t.chip(
        sourceName(hood, t.manual, t.collectors),
        formatDayTime(hood.fetch?.fetched_at ?? post?.first_seen_at ?? finding.created_at),
        mode ? (t.access[mode] ?? mode) : collector,
      )
    : null;

  return (
    <details className="hood" id="pod-maska">
      <summary>
        <span className="hood__title">{t.title}</span>
        <span className="hood__chip">{chip ?? t.lead}</span>
      </summary>
      <div className="hood__body">
        {query.isError ? (
          <p className="hood__muted">{t.error}</p>
        ) : !hood ? (
          <p className="hood__muted">{t.loading}</p>
        ) : (
          <div className="hood__grid">
            <FetchSection hood={hood} />
            <div className="hood__stack">
              <AnalysisSection hood={hood} />
              <TimingsSection hood={hood} />
            </div>
            <StorageSection hood={hood} />
          </div>
        )}
      </div>
    </details>
  );
}
