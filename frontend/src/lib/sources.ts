import type { RegistryStatus, Source } from "@/api/types";
import type { PillTone } from "@/components/StatusPill";
import { pl } from "@/i18n/pl";
import { domainOf, formatLocalDate, isToday } from "@/lib/format";

export type SourceState = keyof typeof pl.sources.states;

/**
 * Display state of a source: works, waits for a key/consent, refused by the site (robots.txt or
 * a TDM reservation; never retried around), off, failing or running.
 */
export function sourceState(source: Source): SourceState {
  if (!source.enabled) return "off";
  if (source.connector_status === "needs_credentials") return "key";
  if (source.connector_status === "needs_approval") return "approval";
  if (source.connector_status === "disabled") return "off";
  const status = source.last_status ?? source.last_run_status;
  if (status === "blocked") return "blocked";
  if (status === "error" || status === "partial") return "error";
  if (status === "running") return "running";
  if (status === "ok") return "ok";
  return "new";
}

/** Cron expression in plain Polish where it is a common pattern ("co 6 godz."). */
export function describeCron(cron: string): string {
  const c = pl.sources.cron;
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return cron;
  const [minute, hour, dom, month, dow] = parts as [string, string, string, string, string];
  if (dom !== "*" || month !== "*" || dow !== "*") return cron;
  const everyMin = /^\*\/(\d+)$/.exec(minute);
  if (everyMin && hour === "*") return c.everyMinutes(Number(everyMin[1]));
  const everyHour = /^\*\/(\d+)$/.exec(hour);
  if (/^\d+$/.test(minute) && everyHour) return c.everyHours(Number(everyHour[1]));
  if (/^\d+$/.test(minute) && hour === "*") return c.everyHours(1);
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour))
    return c.daily(`${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`);
  return cron;
}

/** Second line of a source row: what it watches and how often. */
export function sourceSubtitle(source: Source): string {
  const target = source.target ?? source.url;
  const what = /^https?:\/\//.test(target) ? domainOf(target) : target;
  const when = describeCron(source.cron ?? source.schedule);
  const text = what ? `${what}, ${when}` : when;
  return text.charAt(0).toLocaleUpperCase("pl") + text.slice(1);
}

/** Items seen today across sources (by their last run). */
export function checkedToday(sources: readonly Source[], now: number = Date.now()): number {
  return sources
    .filter((s) => s.last_run_at && isToday(s.last_run_at, now))
    .reduce((sum, s) => sum + s.last_run_items, 0);
}

/** "Sposób dostępu" of a source: by collector, else by the connector's access mode. */
export function accessLabel(source: Source): string {
  return (
    pl.sources.access[source.collector] ??
    (source.access_mode ? pl.sources.accessModes[source.access_mode] : source.collector)
  );
}

/** Sources waiting for a key or a platform's consent. */
export const isWaiting = (source: Source): boolean => {
  const state = sourceState(source);
  return state === "key" || state === "approval";
};

/**
 * State of the "Rejestr KNF" row: live sync works; offline it is a copy (the committed
 * snapshot), which says from when; no sync or an error is a failure.
 */
export function registryRowState(registry: RegistryStatus): { tone: PillTone; label: string } {
  const sync = registry.last_sync;
  if (!registry.synced_at || !sync || sync.error) {
    return { tone: "high", label: pl.sources.states.error };
  }
  if (sync.source === "snapshot") {
    return {
      tone: "medium",
      label: pl.sources.registryRow.snapshot(formatLocalDate(sync.fetched_at)),
    };
  }
  return { tone: "ok", label: pl.sources.states.ok };
}
