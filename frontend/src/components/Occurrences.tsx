import type { FindingWithPost } from "@/api/types";
import { pl } from "@/i18n/pl";
import { formatHistoryTime } from "@/lib/format";

/** "Wystąpienia" card: every location of the material (shown when there is more than one). */
export function Occurrences({ finding }: { finding: FindingWithPost }) {
  const list = finding.occurrences ?? [];
  if (list.length < 2) return null;
  const first = finding.first_seen_at ?? list[0]?.first_seen_at;
  const last = finding.last_seen_at ?? list[0]?.last_seen_at;
  return (
    <section className="card" data-testid="occurrences-card">
      <h2 className="h3 card__title">{pl.finding.occurrences.title(list.length)}</h2>
      <p className="note">{pl.finding.occurrences.lead}</p>
      {first && last && (
        <p>{pl.finding.occurrences.range(formatHistoryTime(first), formatHistoryTime(last))}</p>
      )}
      <ol className="occurrences">
        {list.map((o) => (
          <li key={o.post_id}>
            <span>
              {o.url.includes("://") ? (
                <a href={o.url} target="_blank" rel="noreferrer noopener">
                  {o.url}
                </a>
              ) : (
                o.url
              )}{" "}
              · {o.author} · {pl.platforms[o.platform]}
            </span>
            <span className="history__time">
              {pl.finding.occurrences.seen(
                formatHistoryTime(o.first_seen_at),
                formatHistoryTime(o.last_seen_at),
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
