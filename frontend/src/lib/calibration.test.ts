import { describe, expect, it } from "vitest";
import type { CalibrationPoint, CalibrationReport } from "@/api/types";
import {
  bestThreshold,
  fBeta,
  histogramRows,
  pointAt,
  prCurve,
  precisionRecall,
  riskLevelFor,
  snapThreshold,
  thresholdRows,
} from "@/lib/calibration";
import calibrationJson from "@/mocks/fixtures/calibration.json";

const report = calibrationJson as unknown as CalibrationReport;

const point = (
  threshold: number,
  tp: number,
  fp: number,
  fn: number,
  tn: number,
): CalibrationPoint => {
  const [precision, recall] = precisionRecall(tp, fp, fn);
  return {
    threshold,
    tp,
    fp,
    fn,
    tn,
    precision,
    recall,
    f1: fBeta(tp, fp, fn, 1),
    f2: fBeta(tp, fp, fn, 2),
  };
};

describe("calibration math", () => {
  it("computes precision, recall and F-scores from a confusion matrix", () => {
    const [precision, recall] = precisionRecall(47, 12, 1);
    expect(precision).toBeCloseTo(0.7966, 4);
    expect(recall).toBeCloseTo(0.9792, 4);
    expect(fBeta(47, 12, 1, 1)).toBeCloseTo(0.8785, 4);
    expect(fBeta(47, 12, 1, 2)).toBeCloseTo(0.9363, 4);
    expect(fBeta(0, 0, 0, 1)).toBe(0);
  });

  it("agrees with every point of the calibration fixture", () => {
    for (const p of report.points) {
      expect(p.tp + p.fp + p.fn + p.tn).toBe(report.n_labels);
      expect(fBeta(p.tp, p.fp, p.fn, 1)).toBeCloseTo(p.f1, 3);
      expect(fBeta(p.tp, p.fp, p.fn, 2)).toBeCloseTo(p.f2, 3);
    }
  });

  it("finds the nearest point and snaps to the 0.01 grid", () => {
    expect(snapThreshold(0.7349)).toBe(0.73);
    expect(snapThreshold(1.2)).toBe(1);
    expect(pointAt(report.points, 0.5)?.threshold).toBe(0.5);
    expect(pointAt(report.points, 0.504)?.threshold).toBe(0.5);
    expect(pointAt([], 0.5)).toBeUndefined();
  });

  it("recommends the F1/F2-optimal thresholds of the fixture", () => {
    expect(bestThreshold(report.points, "f1")).toBeCloseTo(report.recommended_f1, 2);
    expect(bestThreshold(report.points, "f2")).toBeCloseTo(report.recommended_f2, 2);
  });

  it("breaks F1 ties towards the lower threshold", () => {
    const points = [point(0.3, 8, 2, 2, 8), point(0.6, 8, 2, 2, 8), point(0.9, 2, 0, 8, 10)];
    expect(bestThreshold(points, "f1")).toBe(0.3);
  });

  it("maps scores to risk levels with a 0.2 medium band", () => {
    expect(riskLevelFor(0.7, 0.7)).toBe("high");
    expect(riskLevelFor(0.55, 0.7)).toBe("medium");
    expect(riskLevelFor(0.49, 0.7)).toBe("low");
  });

  it("orders the PR curve by recall without duplicates", () => {
    const curve = prCurve(report.points);
    const recalls = curve.map((p) => p.recall);
    expect(recalls).toEqual([...recalls].sort((a, b) => a - b));
    expect(curve.length).toBeLessThanOrEqual(report.points.length);
  });

  it("splits histogram bins into labelled and unlabelled counts", () => {
    const rows = histogramRows([{ lo: 0, hi: 0.05, count: 12, positives: 1, negatives: 2 }]);
    expect(rows[0]).toMatchObject({ positives: 1, negatives: 2, unlabeled: 9, mid: 0.025 });
  });
});

describe("thresholdRows", () => {
  it("keeps the slider range, ascending, with counts and percentages", () => {
    const rows = thresholdRows([
      point(0.5, 8, 2, 2, 8),
      point(0.02, 10, 10, 0, 0),
      point(0.3, 9, 3, 1, 7),
    ]);
    expect(rows.map((r) => r.threshold)).toEqual([0.3, 0.5]);
    expect(rows[1]).toMatchObject({
      found: 8,
      falseAlarms: 2,
      missed: 2,
      recall: 80,
      precision: 80,
    });
  });
  it("matches the fixture's point count inside 0.05–0.95", () => {
    const rows = thresholdRows(report.points);
    expect(rows.length).toBe(
      report.points.filter((p) => p.threshold >= 0.05 && p.threshold <= 0.95).length,
    );
    expect(rows.every((r, i) => i === 0 || r.threshold > (rows[i - 1]?.threshold ?? 0))).toBe(true);
  });
});
