import type { ServiceStatus, SystemStatus } from "@/api/types";
import { pl } from "@/i18n/pl";
import { count } from "@/lib/plural";

const t = pl.system;

/** Second line of a service tile: what is running (Polish), or the state when it is not ok. */
export function serviceLine(
  service: ServiceStatus,
  status: SystemStatus,
  now = Date.now(),
): string {
  if (service.state !== "ok") return t.states[service.state];
  switch (service.name) {
    case "workers": {
      const n = Number(service.detail);
      return Number.isFinite(n) && n > 0 ? count(n, t.workerNoun) : t.states.ok;
    }
    case "beat": {
      if (!status.beat_last_tick) return t.states.ok;
      const s = Math.max(0, Math.round((now - Date.parse(status.beat_last_tick)) / 1000));
      return t.tick(s);
    }
    case "minio":
      return service.detail === "memory" ? t.memory : t.bucket(service.detail ?? "");
    case "redis":
    case "api":
      return t.states.ok;
    default:
      return service.detail ?? t.states.ok;
  }
}
