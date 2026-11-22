from __future__ import annotations

from investwatch_ai.review import LlmRuleVerdict, _merge, output_schema
from investwatch_ai.schemas import RuleResult


def _rule(rule_id: str, status: str) -> RuleResult:
    return RuleResult.model_validate(
        {
            "rule_id": rule_id,
            "name": "r",
            "status": status,
            "confidence": 0.5,
            "check_type": "text",
            "weight": 0.4,
            "explanation": "z reguły",
            "legal_basis": "art. 44",
            "evidence": [],
        }
    )


def test_output_schema_requires_exactly_the_rules_asked() -> None:
    schema = output_schema([_rule("2", "unknown"), _rule("11", "unknown")])
    rules = schema["properties"]["rules"]
    assert rules["minItems"] == rules["maxItems"] == 2
    assert schema["$defs"]["LlmRuleVerdict"]["properties"]["rule_id"]["enum"] == ["2", "11"]


def test_unquotable_fail_keeps_a_text_fail_but_not_an_unknown() -> None:
    verdict = LlmRuleVerdict(
        rule_id="2", status="fail", confidence=0.9, explanation="x", quote="nie ma w tekście"
    )
    kept = _merge(_rule("2", "fail"), verdict, "Zarabiaj 40% rocznie.")
    assert kept.status == "fail" and kept.explanation == "z reguły"
    dropped = _merge(_rule("2", "unknown"), verdict, "Zarabiaj 40% rocznie.")
    assert dropped.status == "unknown" and dropped.check_type == "llm"
