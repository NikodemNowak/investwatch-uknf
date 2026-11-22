"""Threshold calibration from labels. Pure functions, no I/O.

The same confusion / F-beta arithmetic as `ai/src/investwatch_ai/eval/metrics.py`, which
evaluates the golden set offline; here it runs on the `labels` table on every request.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from investwatch.core.schemas import (
    CalibrationPoint,
    CalibrationReport,
    HistogramBin,
    ModuleId,
)

STEPS = 100
"""Thresholds 0.00, 0.01, ..., 1.00."""
HISTOGRAM_BINS = 20
MIN_LABELS = 20
EPS = 1e-9


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def _f_beta(precision: float, recall: float, beta: float) -> float:
    b2 = beta * beta
    den = b2 * precision + recall
    return (1 + b2) * precision * recall / den if den else 0.0


def point(scored: Sequence[tuple[float, int]], threshold: float) -> CalibrationPoint:
    """Confusion and metrics when `score >= threshold` raises an alert."""
    tp = fp = fn = tn = 0
    for score, label in scored:
        alert = score >= threshold - EPS
        if label and alert:
            tp += 1
        elif alert:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return CalibrationPoint(
        threshold=threshold,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(_f_beta(precision, recall, 1.0), 4),
        f2=round(_f_beta(precision, recall, 2.0), 4),
    )


def best(points: Iterable[CalibrationPoint], metric: str, default: float) -> float:
    """Threshold with the highest F1 or F2; the highest among ties (fewer alerts).

    Threshold 0 is never recommended. `default` when no threshold reaches a positive score
    (no labels or no positives).
    """
    best_t, best_v = default, 0.0
    for p in points:
        if p.threshold <= 0:
            continue  # threshold 0 alerts on everything, including posts with no finding
        value = float(getattr(p, metric))
        if value > 0 and value >= best_v:
            best_t, best_v = p.threshold, value
    return best_t


def histogram(
    all_scores: Iterable[float], labelled: Iterable[tuple[float, int]], bins: int = HISTOGRAM_BINS
) -> list[HistogramBin]:
    """Score histogram: `count` over every scored record, split by label where known."""

    def index(score: float) -> int:
        return min(bins - 1, max(0, int(score * bins + EPS)))

    counts = [0] * bins
    positives = [0] * bins
    negatives = [0] * bins
    for score in all_scores:
        counts[index(score)] += 1
    for score, label in labelled:
        if label:
            positives[index(score)] += 1
        else:
            negatives[index(score)] += 1
    return [
        HistogramBin(
            lo=round(i / bins, 4),
            hi=round((i + 1) / bins, 4),
            count=counts[i],
            positives=positives[i],
            negatives=negatives[i],
        )
        for i in range(bins)
    ]


def build_report(
    module: ModuleId,
    labelled: Sequence[tuple[float, int]],
    unlabelled_scores: Iterable[float],
    current_threshold: float,
    labels_by_source: dict[str, int] | None = None,
) -> CalibrationReport:
    """Calibration curve, recommendations and histogram for one module.

    Args:
        module: The module.
        labelled: (score, label) of every labelled item (label 1 = violation).
        unlabelled_scores: Scores of the module's records without a label (histogram only).
        current_threshold: The threshold in force (`settings`).
        labels_by_source: Label counts per source, passed through to the report.
    """
    points = [point(labelled, round(i / STEPS, 2)) for i in range(STEPS + 1)]
    return CalibrationReport(
        module=module,
        n_labels=len(labelled),
        n_positive=sum(1 for _, label in labelled if label),
        current_threshold=current_threshold,
        recommended_f1=best(points, "f1", current_threshold),
        recommended_f2=best(points, "f2", current_threshold),
        points=points,
        histogram=histogram([*unlabelled_scores, *(score for score, _ in labelled)], labelled),
        min_labels=MIN_LABELS,
        labels_by_source=labels_by_source or {},
    )
