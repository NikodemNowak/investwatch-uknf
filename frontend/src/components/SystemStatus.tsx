import type { ServiceState } from "@/api/types";
import { useSystem } from "@/hooks/useSystem";
import { pl } from "@/i18n/pl";
import { formatTime, formatWhen } from "@/lib/format";
import { serviceLine } from "@/lib/system";

const t = pl.system;
const DOT: Record<ServiceState, string> = {
  ok: "dot",
  degraded: "dot dot--warn",
  down: "dot dot--bad",
  disabled: "dot dot--off",
};

/** "Stan systemu" on Monitoring: every service, the queues and the next scheduled run. */
export function SystemStatus() {
  const query = useSystem();
  const status = query.data;
  if (query.isError) return <p className="note">{t.error}</p>;
  if (!status) {
    return (
      <section className="card system system--loading" aria-busy="true">
        <h2 className="h3">{t.title}</h2>
        <p className="note">{t.checking}</p>
      </section>
    );
  }
  return (
    <section className="card system" aria-labelledby="system-h">
      <div className="system__head">
        <h2 id="system-h" className="h3">
          {t.title}
        </h2>
        <span className="note">{t.checked(formatTime(status.checked_at))}</span>
      </div>
      <ul className="system__services">
        {status.services.map((s) => (
          <li
            key={s.name}
            className="system__service"
            title={[t.states[s.state], s.detail].filter(Boolean).join(": ")}
          >
            <span className={DOT[s.state]} aria-hidden="true" />
            <span className="system__name">{t.services[s.name] ?? s.name}</span>
            <span className="system__state">{serviceLine(s, status)}</span>
          </li>
        ))}
      </ul>
      <div className="system__foot">
        <span>
          {status.next_run
            ? t.nextRun(
                status.next_run.source_name,
                formatWhen(status.next_run.at),
                status.next_run.cron,
              )
            : t.noNextRun}
        </span>
        {status.queues.length > 0 && (
          <span>
            {t.queues}: {status.queues.map((q) => `${q.name} (${q.workers.length})`).join(", ")}
          </span>
        )}
        {status.ai?.llm_model && status.ai.embed_model && (
          <span>{t.models(status.ai.llm_model, status.ai.embed_model)}</span>
        )}
      </div>
    </section>
  );
}
