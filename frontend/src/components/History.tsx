import type { FindingWithPost } from "@/api/types";
import { pl } from "@/i18n/pl";
import { formatHistoryTime } from "@/lib/format";
import { llmReviewOf } from "@/lib/problems";

/** "Historia" card built from the post, trace and model review times. */
export function History({ finding }: { finding: FindingWithPost }) {
  const post = finding.post;
  const trace = finding.trace;
  const review = llmReviewOf(finding);
  const analyzedAt = trace?.analyzed_at ?? finding.created_at;
  const shotViewports = new Set(
    finding.rules.flatMap((rule) =>
      rule.check_type === "render" ? rule.evidence.map((e) => e.viewport).filter(Boolean) : [],
    ),
  );
  const events: { time: string; text: string }[] = [];
  if (post) events.push({ time: post.first_seen_at, text: pl.finding.events.seen(post.collector) });
  events.push({
    time: analyzedAt,
    text: shotViewports.size
      ? pl.finding.events.measured(
          Math.max(shotViewports.size, Object.keys(post?.screenshot_keys ?? {}).length),
        )
      : pl.finding.events.analyzed(finding.rules.length),
  });
  if (review === "done")
    events.push({ time: trace?.llm?.finished_at ?? analyzedAt, text: pl.finding.events.llmDone });
  if (review === "queued") events.push({ time: analyzedAt, text: pl.finding.events.llmQueued });
  if (review === "unavailable")
    events.push({
      time: trace?.llm?.finished_at ?? analyzedAt,
      text: pl.finding.events.llmUnavailable,
    });
  events.sort((a, b) => a.time.localeCompare(b.time));
  return (
    <section className="card">
      <h2 className="h3 card__title">{pl.finding.history}</h2>
      <ol className="history">
        {events.map((event, index) => (
          <li key={index}>
            <span className="history__time">{formatHistoryTime(event.time)}</span>
            <span>{event.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
