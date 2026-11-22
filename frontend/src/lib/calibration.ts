import type { CalibrationPoint, HistogramBin, RiskLevel } from "@/api/types";

/** Band below the threshold that still counts as medium risk (plan 3.10). */
export const MEDIUM_BAND = 0.2;

/** Round to the 0.01 grid the calibration points use. */
export function snapThreshold(value: number): number {
  return Math.min(1, Math.max(0, Math.round(value * 100) / 100));
}

/** The calibration point closest to `threshold`, or undefined for an empty list. */
export function pointAt(
  points: readonly CalibrationPoint[],
  threshold: number,
): CalibrationPoint | undefined {
  let best: CalibrationPoint | undefined;
  for (const point of points) {
    if (!best || Math.abs(point.threshold - threshold) < Math.abs(best.threshold - threshold)) {
      best = point;
    }
  }
  return best;
}

/** F-beta score from a confusion matrix; 0 when undefined. */
export function fBeta(tp: number, fp: number, fn: number, beta: number): number {
  const b2 = beta * beta;
  const denom = (1 + b2) * tp + b2 * fn + fp;
  return denom === 0 ? 0 : ((1 + b2) * tp) / denom;
}

/** Precision and recall from a confusion matrix; precision is 1 when nothing is flagged. */
export function precisionRecall(tp: number, fp: number, fn: number): [number, number] {
  const precision = tp + fp === 0 ? 1 : tp / (tp + fp);
  const recall = tp + fn === 0 ? 0 : tp / (tp + fn);
  return [precision, recall];
}

/** Threshold maximising F1 or F2; ties go to the lowest threshold (recall first, as the backend). */
export function bestThreshold(points: readonly CalibrationPoint[], metric: "f1" | "f2"): number {
  let best: CalibrationPoint | undefined;
  for (const point of points) {
    if (
      !best ||
      point[metric] > best[metric] ||
      (point[metric] === best[metric] && point.threshold < best.threshold)
    ) {
      best = point;
    }
  }
  return best?.threshold ?? 0.5;
}

/** Risk level for a score under threshold τ: high ≥ τ, medium ≥ τ − 0.2, else low. */
export function riskLevelFor(score: number, threshold: number): RiskLevel {
  if (score >= threshold) return "high";
  if (score >= threshold - MEDIUM_BAND) return "medium";
  return "low";
}

export interface PrCurvePoint {
  threshold: number;
  recall: number;
  precision: number;
}

/** PR curve points ordered by recall (x axis), one per distinct (recall, precision). */
export function prCurve(points: readonly CalibrationPoint[]): PrCurvePoint[] {
  const seen = new Set<string>();
  const out: PrCurvePoint[] = [];
  for (const p of [...points].sort((a, b) => a.recall - b.recall || b.precision - a.precision)) {
    const key = `${p.recall.toFixed(4)}:${p.precision.toFixed(4)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ threshold: p.threshold, recall: p.recall, precision: p.precision });
  }
  return out;
}

export interface HistogramRow {
  label: string;
  mid: number;
  positives: number;
  negatives: number;
  unlabeled: number;
}

/** Split each bin into labelled positives, labelled negatives and unlabelled records. */
export function histogramRows(bins: readonly HistogramBin[]): HistogramRow[] {
  return bins.map((bin) => ({
    label: `${bin.lo.toFixed(2)}–${bin.hi.toFixed(2)}`,
    mid: (bin.lo + bin.hi) / 2,
    positives: bin.positives,
    negatives: bin.negatives,
    unlabeled: Math.max(0, bin.count - bin.positives - bin.negatives),
  }));
}

export interface ThresholdRow {
  threshold: number;
  found: number;
  falseAlarms: number;
  missed: number;
  /** Percent, 0–100. */
  recall: number;
  /** Percent, 0–100; 100 when nothing is flagged (as the precision card). */
  precision: number;
}

/** Chart rows for thresholds in [min, max]: counts and rates, ascending threshold. */
export function thresholdRows(
  points: readonly CalibrationPoint[],
  min = 0.05,
  max = 0.95,
): ThresholdRow[] {
  return [...points]
    .filter((p) => p.threshold >= min - 1e-9 && p.threshold <= max + 1e-9)
    .sort((a, b) => a.threshold - b.threshold)
    .map((p) => {
      const [precision, recall] = precisionRecall(p.tp, p.fp, p.fn);
      return {
        threshold: snapThreshold(p.threshold),
        found: p.tp,
        falseAlarms: p.fp,
        missed: p.fn,
        recall: Math.round(recall * 1000) / 10,
        precision: Math.round(precision * 1000) / 10,
      };
    });
}
