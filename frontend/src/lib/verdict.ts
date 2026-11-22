/**
 * Final verdict shown on the check page and in banners: combines the risk level, the rule
 * problems and the model signal (see problems.ts) into one headline plus supporting text.
 */
import type { FindingWithPost, RiskLevel } from "@/api/types";
import { pl } from "@/i18n/pl";
import type { CheckPhase } from "@/lib/checkSteps";
import {
  modelSignalOf,
  pendingNames,
  plainExplanation,
  problemsOf,
  summaryOf,
} from "@/lib/problems";
import type { ModelSignal, Problem } from "@/lib/problems";

const RANK: Record<RiskLevel, number> = { high: 3, medium: 2, low: 1 };

/** The finding to open for a checked page: highest risk, then highest score. */
export function primaryFinding(findings: readonly FindingWithPost[]): FindingWithPost | undefined {
  return [...findings].sort(
    (a, b) => RANK[b.risk_level] - RANK[a.risk_level] || b.score - a.score,
  )[0];
}

export interface Verdict {
  risk: RiskLevel | null;
  headline: string;
  text: string;
  problems: Problem[];
  /** No failed requirement but a high / medium risk: why (the model or content markers). */
  signal: ModelSignal | null;
  /** Requirements the model is still reading. */
  pending: string[];
}

/** What the check found on one page, across its findings (one per module). */
export function verdictOf(findings: readonly FindingWithPost[], phase: CheckPhase): Verdict {
  const ordered = [...findings].sort(
    (a, b) => RANK[b.risk_level] - RANK[a.risk_level] || b.score - a.score,
  );
  const seen = new Set<string>();
  const problems: Problem[] = [];
  for (const finding of ordered) {
    if (finding.risk_level === "low") continue;
    for (const problem of problemsOf(finding.rules)) {
      if (seen.has(problem.title)) continue;
      seen.add(problem.title);
      problems.push(problem);
    }
  }
  const pending = [...new Set(ordered.flatMap((f) => pendingNames(f.rules)))];
  const primary = ordered[0];
  const risk = primary?.risk_level ?? null;
  const signal = problems.length === 0 && primary ? modelSignalOf(primary) : null;
  // Same wording as the finding page; "preliminary" is the banner label, not the headline.
  const headline =
    risk === null
      ? pl.check.headline.low
      : (signal?.title ?? pl.finding.banner[risk](problems.length));
  const base = problems.length ? summaryOf(problems) : primary ? plainExplanation(primary) : "";
  const text =
    phase === "preliminary" ? `${base} ${pl.check.llmPendingSuffix(pending.length)}`.trim() : base;
  return { risk, headline, text, problems, signal, pending };
}
