"""Rule engine: metadata (weights, legal basis) from risk_rules.yaml; checks use `@rule`.

Text/lexicon patterns live in lexicon_pl.yaml; `evaluate` runs a set of rule ids over a
`RuleContext` and returns `RuleResult`s (`pass` / `fail` / `unknown` / `na`).
"""

from . import checks as _checks  # noqa: F401  (registers the rule functions)
from .registry import (
    M1_RULE_IDS,
    M2_RULE_IDS,
    M3_ELEMENT_IDS,
    RuleContext,
    RuleMeta,
    evaluate,
    load_lexicon,
    load_rules,
    load_rules_file,
    registered,
    rule,
)

__all__ = [
    "M1_RULE_IDS",
    "M2_RULE_IDS",
    "M3_ELEMENT_IDS",
    "RuleContext",
    "RuleMeta",
    "evaluate",
    "load_lexicon",
    "load_rules",
    "load_rules_file",
    "registered",
    "rule",
]
