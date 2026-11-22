"""Confusion counts and precision / recall / F-beta (pure functions, no I/O)."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    """Binary confusion counts."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def n(self) -> int:
        """Number of scored items."""
        return self.tp + self.fp + self.fn + self.tn

    @property
    def positives(self) -> int:
        """Items labelled positive."""
        return self.tp + self.fn

    @property
    def precision(self) -> float:
        """TP / (TP + FP); 0 when nothing was predicted positive."""
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); 0 when there are no positives."""
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    def f_beta(self, beta: float) -> float:
        """Weighted harmonic mean of precision and recall (beta > 1 favours recall)."""
        p, r = self.precision, self.recall
        b2 = beta * beta
        return (1 + b2) * p * r / (b2 * p + r) if p + r else 0.0

    @property
    def f1(self) -> float:
        """F1 score."""
        return self.f_beta(1.0)

    @property
    def f2(self) -> float:
        """F2 score (recall weighted twice as much: a supervisor would rather not miss)."""
        return self.f_beta(2.0)

    def __add__(self, other: Confusion) -> Confusion:
        return Confusion(
            self.tp + other.tp, self.fp + other.fp, self.fn + other.fn, self.tn + other.tn
        )


def confusion(pairs: Iterable[tuple[bool, bool]]) -> Confusion:
    """Count (label, predicted) pairs."""
    tp = fp = fn = tn = 0
    for label, predicted in pairs:
        if label and predicted:
            tp += 1
        elif predicted:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    return Confusion(tp, fp, fn, tn)


def at_threshold(scored: Iterable[tuple[float, bool]], threshold: float) -> Confusion:
    """Confusion when `score >= threshold` means positive."""
    return confusion((label, score >= threshold - 1e-9) for score, label in scored)


def sweep(scored: list[tuple[float, bool]], steps: int = 100) -> list[tuple[float, Confusion]]:
    """Confusion at thresholds 0.00, 0.01, ..., 1.00."""
    return [(round(i / steps, 2), at_threshold(scored, i / steps)) for i in range(steps + 1)]


def best_threshold(
    curve: list[tuple[float, Confusion]], beta: float, default: float = 0.5
) -> float:
    """Threshold with the highest F-beta (the highest among ties: fewer alerts).

    Returns `default` when no threshold reaches a positive F-beta (e.g. no positive labels).
    """
    best_t, best_f = default, 0.0
    for t, c in curve:
        if t <= 0:
            continue  # threshold 0 flags everything, including items with no finding
        f = c.f_beta(beta)
        if f > 0 and f >= best_f:
            best_t, best_f = t, f
    return best_t


def bootstrap_ci(
    pairs: list[tuple[bool, bool]],
    stat: Callable[[Confusion], float],
    reps: int = 2000,
    seed: int = 20261121,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap interval of a confusion statistic over (label, predicted) pairs.

    Resamples items with replacement; with a handful of positives the interval is wide, and
    that width is the honest message.
    """
    if not pairs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(pairs)
    values = sorted(stat(confusion(rng.choices(pairs, k=n))) for _ in range(reps))
    lo = values[int(alpha / 2 * reps)]
    hi = values[min(reps - 1, int((1 - alpha / 2) * reps))]
    return (lo, hi)
