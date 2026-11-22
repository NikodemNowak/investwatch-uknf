import type { FindingWithPost, JobStage, Post, ReviewQueuePosition } from "@/api/types";
import { pl } from "@/i18n/pl";
import { VIEWPORTS } from "@/lib/enums";
import { domainOf, formatContrast, formatNumber, formatSeconds } from "@/lib/format";
import { llmReviewOf, warningMeasures } from "@/lib/problems";

export type StepState = "done" | "run" | "wait" | "skip" | "fail";
export type StepKey = "fetch" | "firm" | "shots" | "measure" | "llm" | "final";

export interface CheckStep {
  key: StepKey;
  state: StepState;
  label: string;
  detail: string;
}

export type CheckPhase = "pending" | "preliminary" | "final" | "failed" | "duplicate";

/** Everything known about a running check, as collected from events and fetches. */
export interface CheckSnapshot {
  url: string;
  startedAt: number;
  /** When each stage was first seen (client clock). */
  stages: Partial<Record<JobStage, number>>;
  post: Post | null;
  /** Findings of the job once loaded (empty for a duplicate), else null. */
  findings: FindingWithPost[] | null;
  duplicate: boolean;
  /** Where the model review of the primary finding waits (null: not asked yet). */
  reviewQueue?: ReviewQueuePosition | null;
}

export interface CheckProgress {
  steps: CheckStep[];
  done: number;
  total: number;
  phase: CheckPhase;
  finished: boolean;
}

const ORDER: StepKey[] = ["fetch", "firm", "shots", "measure", "llm", "final"];

/** Fold a check snapshot into the six steps of the "Postęp" card. */
export function checkProgress(s: CheckSnapshot): CheckProgress {
  const d = pl.check.detail;
  const analyzed = s.stages.analyzed !== undefined && s.findings !== null;
  const findings = s.findings ?? [];
  const reviews = findings.map(llmReviewOf);
  const llmQueued = reviews.includes("queued");
  const failed = s.stages.failed !== undefined;

  const shotNames = VIEWPORTS.filter((v) => s.post?.screenshot_keys[v]).map((v, i) =>
    i === 0 ? pl.viewports[v] : pl.viewports[v].toLocaleLowerCase("pl"),
  );
  const raw: Record<StepKey, boolean> = {
    fetch: s.stages.fetched !== undefined || analyzed || s.post !== null,
    firm: analyzed,
    shots: shotNames.length > 0 || analyzed,
    measure: analyzed,
    llm: analyzed && !llmQueued,
    final: analyzed && !llmQueued,
  };

  const details: Record<StepKey, string> = {
    fetch:
      s.stages.fetched !== undefined
        ? d.fetchDone(domainOf(s.post?.url ?? s.url), formatSeconds(s.stages.fetched - s.startedAt))
        : domainOf(s.post?.url ?? s.url),
    firm: d.firmRun,
    shots: d.shotsRun,
    measure: d.measureRun,
    llm: d.llmWaiting,
    final: d.finalWait,
  };
  const queue = s.reviewQueue;
  const waitingInQueue = analyzed && llmQueued && queue?.state === "queued";
  if (analyzed && llmQueued && queue) {
    if (queue.state === "queued") details.llm = d.llmQueued(queue.ahead);
    else if (queue.state === "running") details.llm = d.llmRun;
  }
  if (raw.firm) {
    const withFirm = [...findings]
      .sort((a, b) => b.score - a.score)
      .find((finding) => finding.firm);
    details.firm = withFirm?.firm
      ? withFirm.firm.fictional
        ? d.firmFictional(withFirm.firm.name)
        : d.firmFound(withFirm.firm.name)
      : findings.some((f) => f.module === "m3_shadow_advisory" && f.risk_level !== "low")
        ? d.firmMissing
        : d.firmNone;
  }
  if (raw.shots) details.shots = shotNames.length ? d.shots(shotNames) : d.shotsNone;
  if (raw.measure) {
    const m = warningMeasures(findings.flatMap((f) => f.rules));
    const parts: string[] = [];
    if (m.warningPx !== undefined) parts.push(`${formatNumber(m.warningPx)} px`);
    if (m.contrast !== undefined) parts.push(`kontrast ${formatContrast(m.contrast)}`);
    if (m.inFooter) parts.push("w stopce");
    const ruleIds = new Set(
      findings.flatMap((f) => f.rules.map((r) => `${f.module}:${r.rule_id}`)),
    );
    details.measure = parts.length
      ? parts.join(", ")
      : ruleIds.size
        ? d.measureRules(ruleIds.size)
        : d.measureNone;
  }
  let llmSkipped = false;
  if (raw.llm) {
    const traced = findings.find((f) => f.trace?.llm)?.trace?.llm;
    if (reviews.includes("done")) {
      const model = traced?.model ?? findings.find((f) => f.used_llm)?.model ?? "";
      const ms = traced?.ms;
      details.llm = d.llmDone(
        model.split("+")[0] ?? model,
        typeof ms === "number" ? formatSeconds(ms) : null,
      );
    } else {
      llmSkipped = true;
      details.llm = reviews.includes("unavailable") ? d.llmUnavailable : d.llmNone;
    }
  }
  if (raw.final) details.final = s.duplicate ? d.finalDuplicate : d.finalDone;

  const steps: CheckStep[] = [];
  let blocked = false;
  for (const key of ORDER) {
    const labels = pl.check.steps[key];
    let state: StepState;
    if (!blocked && raw[key]) state = key === "llm" && llmSkipped ? "skip" : "done";
    else if (!blocked) {
      state = failed ? "fail" : "run";
      blocked = true;
    } else state = "wait";
    const label =
      state === "done"
        ? labels.done
        : state === "skip"
          ? pl.check.steps.llm.skipped
          : key === "llm" && state === "run" && waitingInQueue
            ? pl.check.steps.llm.queued
            : state === "run" || state === "fail"
              ? labels.run
              : labels.wait;
    const detail =
      state === "wait" && key !== "final" ? "" : state === "fail" ? d.failed : details[key];
    steps.push({ key, state, label, detail });
  }

  const done = steps.filter((step) => step.state === "done" || step.state === "skip").length;
  const phase: CheckPhase = failed
    ? "failed"
    : !analyzed
      ? "pending"
      : s.duplicate && findings.length === 0
        ? "duplicate"
        : llmQueued
          ? "preliminary"
          : "final";
  return { steps, done, total: ORDER.length, phase, finished: failed || raw.final };
}
