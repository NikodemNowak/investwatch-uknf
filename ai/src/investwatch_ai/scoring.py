"""Scores and risk levels.

Rule results are combined with a noisy-OR (independent evidence); the score is then mapped to
`low` / `medium` / `high` against a per-module threshold (see `risk_level`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from .schemas import RiskLevel, RuleResult

MEDIUM_BAND = 0.2
"""`medium` covers [threshold - band, threshold), band = min(0.2, threshold / 2): with a low
trained threshold (M3 0.12) a fixed 0.2 band would make every finding at least medium."""


def noisy_or(probabilities: Iterable[float]) -> float:
    """Combine independent evidence: 1 - prod(1 - p_i). Empty input gives 0."""
    keep = 1.0
    for p in probabilities:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"probability out of range: {p}")
        keep *= 1.0 - p
    return 1.0 - keep


def rules_score(rules: Iterable[RuleResult]) -> float:
    """M2 score: noisy-OR of weight x confidence over failed rules; pass/na/unknown count 0."""
    return noisy_or(r.weight * r.confidence for r in rules if r.status == "fail")


def risk_level(score: float, threshold: float) -> RiskLevel:
    """`high` at or above the module threshold, `medium` just below it, else `low`."""
    if score >= threshold:
        return "high"
    if score >= threshold - min(MEDIUM_BAND, threshold / 2) - 1e-9:
        return "medium"
    return "low"


def advisory_score(weighted_sum: float, *, bias: float, scale: float) -> float:
    """M3 score: logistic function of the weighted art. 76 elements."""
    return 1.0 / (1.0 + math.exp(-(bias + scale * weighted_sum)))
