from __future__ import annotations

import math

import pytest

from investwatch_ai.schemas import RuleResult
from investwatch_ai.scoring import advisory_score, noisy_or, risk_level, rules_score


def _rr(status: str, weight: float, confidence: float = 1.0) -> RuleResult:
    return RuleResult(
        rule_id="x",
        name="x",
        status=status,  # type: ignore[arg-type]
        confidence=confidence,
        check_type="text",
        weight=weight,
        explanation="",
        legal_basis="",
        evidence=[],
    )


def test_noisy_or_empty_is_zero() -> None:
    assert noisy_or([]) == 0.0


def test_noisy_or_single_and_combination() -> None:
    assert noisy_or([0.9]) == pytest.approx(0.9)
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert noisy_or([0.4, 0.3, 0.2]) == pytest.approx(1 - 0.6 * 0.7 * 0.8)


def test_noisy_or_is_monotone_and_bounded() -> None:
    assert noisy_or([0.2, 0.2, 0.2]) > noisy_or([0.2, 0.2])
    assert noisy_or([1.0, 0.1]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        noisy_or([1.2])


def test_rules_score_counts_only_failures_weighted_by_confidence() -> None:
    rules = [
        _rr("fail", 0.9, 0.8),
        _rr("fail", 0.5, 1.0),
        _rr("pass", 0.9),
        _rr("na", 0.9),
        _rr("unknown", 0.9),
    ]
    assert rules_score(rules) == pytest.approx(1 - (1 - 0.72) * (1 - 0.5))
    assert rules_score([_rr("pass", 1.0), _rr("unknown", 1.0)]) == 0.0


def test_risk_level_bands() -> None:
    assert risk_level(0.6, 0.6) == "high"
    assert risk_level(0.45, 0.6) == "medium"
    assert risk_level(0.4, 0.6) == "medium"
    assert risk_level(0.39, 0.6) == "low"
    # Low trained thresholds: the band is half the threshold, so "low" still exists.
    assert risk_level(0.07, 0.12) == "medium"
    assert risk_level(0.05, 0.12) == "low"
    assert risk_level(0.0, 0.2) == "low"


def test_advisory_score_is_logistic() -> None:
    assert advisory_score(0.0, bias=-2.5, scale=2.0) == pytest.approx(1 / (1 + math.exp(2.5)))
    assert advisory_score(3.5, bias=-2.5, scale=2.0) > 0.98
