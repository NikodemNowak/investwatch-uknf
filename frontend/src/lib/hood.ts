import type { UnderTheHood } from "@/api/types";

const kb = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });

/** Byte size as "812 B", "48,2 kB", "1,4 MB". */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "–";
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${kb.format(bytes / 1000)} kB`;
  return `${kb.format(bytes / 1_000_000)} MB`;
}

/** First characters of a hash, for display (the full value goes in the title). */
export function shortHash(hash: string | null | undefined, length = 12): string {
  if (!hash) return "–";
  return hash.length > length ? `${hash.slice(0, length)}…` : hash;
}

/** A long id (Celery task, run) shortened to its first block. */
export function shortId(id: string | null | undefined): string | null {
  if (!id) return null;
  return id.split("-")[0] ?? id;
}

export interface TimingStep {
  key: string;
  ms: number;
  /** Share of the total, 0–1 (for the bar width). */
  share: number;
}

/** Pipeline order of the `ai` fast pass (JSONB storage does not keep key order). */
const STEP_ORDER = ["preprocess", "rules", "embed", "classifier", "advisory", "llm"];
const rank = (key: string) => {
  const i = STEP_ORDER.indexOf(key);
  return i < 0 ? STEP_ORDER.length : i;
};

/** Pipeline steps from `timings_ms` in pipeline order; `total` becomes the denominator. */
export function timingSteps(timings: Record<string, number> | undefined): {
  steps: TimingStep[];
  total: number;
} {
  const entries = Object.entries(timings ?? {})
    .filter(([key, ms]) => key !== "total" && ms >= 0)
    .sort(([a], [b]) => rank(a) - rank(b));
  const sum = entries.reduce((acc, [, ms]) => acc + ms, 0);
  const total = Math.max(timings?.total ?? 0, sum);
  return {
    steps: entries.map(([key, ms]) => ({ key, ms, share: total > 0 ? ms / total : 0 })),
    total,
  };
}

/** Name of what collected the material: the source, "Sprawdź" or the collector. */
export function sourceName(
  hood: UnderTheHood,
  manualLabel: string,
  collectors: Record<string, string> = {},
): string {
  if (hood.source) return collectors[hood.source.name] ?? hood.source.name;
  const collector = hood.fetch?.collector;
  if (collector === "manual" || hood.collect_job?.job_id) return manualLabel;
  return collector ? (collectors[collector] ?? collector) : "–";
}
