"""Lexicon / rule features of the M1 and M3 classifier heads (pure, no I/O).

The same function feeds training (`make train`) and inference (`analyze()`), so the two can
never drift apart. Features are small numbers in [0, 1]; the heads standardise them.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from ..rules import RuleContext
from ..schemas import RuleResult

HeadId = Literal["m1_third_party_ad", "m3_shadow_advisory"]

M1_CATEGORIES = (
    "ad_label",
    "affiliate_link",
    "referral_phrase",
    "promo_code",
    "cta",
    "bonus",
    "promo_offer",
    "no_promo",
    "gains_claim",
    "risk_warning",
    "past_performance",
    "forecast",
)
M3_CATEGORIES = (
    "advisory_personalised",
    "advisory_instruments",
    "advisory_buy_sell",
    "advisory_management",
    "cta",
    "promo_offer",
    "ad_label",
    "gains_claim",
    "risk_warning",
    "supervisor_mention",
)
M3_ELEMENTS = ("76a", "76b", "76c", "76d", "76e")
DISCLAIMER = re.compile(
    r"\bnie (?:stanowi\w*|jest|są)\s+(?:\w+\s+){0,3}?"
    r"(?:rekomendacj\w*|porad\w*|doradztw\w*|ofert\w*|zachęt\w*)",
    re.IGNORECASE,
)
"""Education / journalism disclaimer ("nie stanowi rekomendacji inwestycyjnej")."""

LABELS_PL: dict[str, str] = {
    "ad_label": "oznaczenie reklamy",
    "affiliate_link": "link afiliacyjny",
    "referral_phrase": "polecenie / kod polecający",
    "promo_code": "kod promocyjny",
    "cta": "wezwanie do działania",
    "bonus": "bonus",
    "promo_offer": "oferta usługi",
    "no_promo": "deklaracja braku współpracy",
    "gains_claim": "obietnica zysku",
    "risk_warning": "ostrzeżenie o ryzyku",
    "past_performance": "wyniki historyczne",
    "forecast": "prognoza",
    "supervisor_mention": "wzmianka o nadzorze",
    "advisory_personalised": "dopasowanie do klienta",
    "advisory_instruments": "instrumenty finansowe",
    "advisory_buy_sell": "wskazania kup / sprzedaj",
    "advisory_management": "zarządzanie cudzym portfelem",
    "rule_2_fail": "brak oznaczenia reklamy",
    "rule_3_fail": "zysk bez ostrzeżenia",
    "el_76a": "element 76a",
    "el_76b": "element 76b",
    "el_76c": "element 76c",
    "el_76d": "element 76d",
    "el_76e": "element 76e",
    "advice_negation": "zastrzeżenie „nie stanowi rekomendacji”",
    "length": "długość tekstu",
    "embedding": "podobieństwo treści (bge-m3)",
}
"""Polish names used in the finding explanation."""


def _count(ctx: RuleContext, category: str) -> float:
    return min(len(ctx.hits(category)), 3) / 3.0


def _length(ctx: RuleContext) -> float:
    return min(math.log1p(len(ctx.text)) / 10.0, 1.0)


def feature_names(head: HeadId) -> tuple[str, ...]:
    """Ordered feature names of a head."""
    if head == "m1_third_party_ad":
        return (*M1_CATEGORIES, "rule_2_fail", "rule_3_fail", "length")
    return (*M3_CATEGORIES, *(f"el_{e}" for e in M3_ELEMENTS), "advice_negation", "length")


def extract(head: HeadId, ctx: RuleContext, rules: list[RuleResult]) -> dict[str, float]:
    """Feature values of one post: lexicon hit counts plus the rule / element verdicts."""
    status = {r.rule_id: r for r in rules}

    def failed(rule_id: str) -> float:
        r = status.get(rule_id)
        return r.confidence if r is not None and r.status == "fail" else 0.0

    if head == "m1_third_party_ad":
        out = {c: _count(ctx, c) for c in M1_CATEGORIES}
        out["rule_2_fail"] = failed("2")
        out["rule_3_fail"] = failed("3")
    else:
        out = {c: _count(ctx, c) for c in M3_CATEGORIES}
        out.update({f"el_{e}": failed(e) for e in M3_ELEMENTS})
        out["advice_negation"] = 1.0 if DISCLAIMER.search(ctx.text) else 0.0
    out["length"] = _length(ctx)
    return out
