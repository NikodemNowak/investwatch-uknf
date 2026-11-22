"""Deterministic stand-in for the `ai` service (used when `AI_MODE=mock` or AI is unreachable).

Keyword heuristics only: good enough to drive the end-to-end path (check URL -> finding ->
alert) and the demo pages; the real rules live in `ai/`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from investwatch.core.schemas import (
    CheckType,
    Evidence,
    Finding,
    FirmMatch,
    ModuleId,
    Post,
    RiskLevel,
    RuleResult,
    RuleStatus,
)
from investwatch.pipeline.schemas import AnalyzeResponse

MOCK_MODEL = "mock-rules-v0"
_NOT_RENDERED = "Wymaga renderu strony (Playwright); w trybie atrapy nie sprawdzono."


@dataclass(frozen=True)
class _RuleSpec:
    rule_id: str
    name: str
    weight: float
    check_type: CheckType
    legal_basis: str


_DEL = "rozporządzenia del. 2017/565"
_ART76 = "art. 76 ustawy o obrocie instrumentami finansowymi"
RULES: dict[str, _RuleSpec] = {
    r.rule_id: r
    for r in [
        _RuleSpec("2", "Oznaczenie reklamy", 0.4, "text", "art. 24 ust. 3 MiFID II"),
        _RuleSpec("3", "Informacja o ryzyku", 0.9, "llm", f"art. 44 ust. 2 lit. b {_DEL}"),
        _RuleSpec("4", "Rozmiar czcionki ryzyka", 0.6, "render", f"art. 44 ust. 2 lit. c {_DEL}"),
        _RuleSpec(
            "6", "Zakrywanie / ukrywanie ryzyka", 0.7, "render", f"art. 44 ust. 2 lit. e {_DEL}"
        ),
        _RuleSpec(
            "14",
            "Ostrzeżenie przy wynikach historycznych",
            0.7,
            "text",
            f"art. 44 ust. 4 lit. d {_DEL}",
        ),
        _RuleSpec("15", "Prognozy przyszłych wyników", 0.7, "llm", f"art. 44 ust. 6 {_DEL}"),
        _RuleSpec("76a", "Rekomendacja spersonalizowana", 0.9, "llm", _ART76),
        _RuleSpec("76c", "Rekomendacja kup / sprzedaj / trzymaj", 0.9, "llm", _ART76),
        _RuleSpec("76e", "Zarządzanie cudzym portfelem", 0.8, "llm", _ART76),
    ]
}

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_GAIN = re.compile(
    r"(zysk|zwrot|zarabia|zarobi|stop[ay] zwrotu|rentowno|rocznie|miesięcznie)"
    r"[^.!?\n]{0,60}\d+([.,]\d+)?\s?%"
    r"|\d+([.,]\d+)?\s?%[^.!?\n]{0,60}(zysk|zwrot|rocznie|miesięcznie|w rok)",
    re.IGNORECASE,
)
_RISK = re.compile(r"ryzyk|traci pieniądze|utrat[ay] (części|całości|kapitału)", re.IGNORECASE)
_PAST = re.compile(
    r"(w (ostatnich|ubiegłym|zeszłym)|w \d{4}|średni[a-z]* (zysk|zwrot|stopa)|historyczn)",
    re.IGNORECASE,
)
_PAST_WARNING = re.compile(
    r"wyniki historyczne nie (są|stanowią)|przeszłe wyniki nie", re.IGNORECASE
)
_FORECAST = re.compile(
    r"gwarant|zarobisz|zrobicie|pewn[ya] zysk|bez ryzyka|minimum \d+\s?%", re.IGNORECASE
)
_AD_MARK = re.compile(
    r"materiał (marketingowy|reklamowy)|#reklama|#ad\b|reklama\b|współpraca reklamowa",
    re.IGNORECASE,
)
_AFFILIATE = re.compile(
    r"aff=|z mojego linku|kod[:\s]|kodem\b|link w opisie|partnerski", re.IGNORECASE
)
_ADVICE_PERSONAL = re.compile(
    r"konsultacj|dobior[ęe]|dopasowan[a-z]* do (twojej|pana|pani)|przejrz[ęe]\w* (twój )?portfel",
    re.IGNORECASE,
)
_ADVICE_BUY = re.compile(
    r"(kup|kupuj|sprzedaj|trzymaj)\w*\b[^.!?\n]{0,40}(akcj|etf|krypto|obligac)", re.IGNORECASE
)
_ADVICE_MANAGE = re.compile(
    r"zarządza\w* (twoim|waszym|cudzym) (kapitałem|portfelem)", re.IGNORECASE
)


def _quote(text: str, pattern: re.Pattern[str]) -> str | None:
    for sentence in _SENTENCE.findall(text):
        if pattern.search(sentence):
            return str(sentence).strip()
    return None


def _rule(
    rule_id: str, status: RuleStatus, explanation: str, quote: str | None = None, conf: float = 0.6
) -> RuleResult:
    spec = RULES[rule_id]
    return RuleResult(
        rule_id=rule_id,
        name=spec.name,
        status=status,
        confidence=conf,
        check_type=spec.check_type,
        weight=spec.weight,
        explanation=explanation,
        legal_basis=spec.legal_basis,
        evidence=[Evidence(quote=quote, viewport=None, bbox=None, measurements={})]
        if quote
        else [],
    )


def noisy_or(rules: list[RuleResult]) -> float:
    """Combine failing rules: 1 - prod(1 - weight * confidence)."""
    keep = 1.0
    for r in rules:
        if r.status == "fail":
            keep *= 1.0 - r.weight * r.confidence
    return round(1.0 - keep, 4)


def risk_level(score: float) -> RiskLevel:
    """Map a score to a risk level."""
    return "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"


def _risk_far_from_claim(text: str) -> bool:
    """Text-only proxy for "warning in the footer": it first appears in the second half."""
    match = _RISK.search(text)
    return match is not None and match.start() / max(len(text), 1) > 0.5


def _m2(text: str) -> list[RuleResult] | None:
    gain = _quote(text, _GAIN)
    if gain is None:
        return None
    rules = []
    if not _RISK.search(text):
        rules.append(_rule("3", "fail", "Twierdzenie o zysku bez informacji o ryzyku.", gain, 0.8))
    elif _risk_far_from_claim(text):
        rules.append(
            _rule("3", "fail", "Ostrzeżenie o ryzyku daleko od twierdzenia o zysku.", gain, 0.7)
        )
    else:
        rules.append(_rule("3", "pass", "Informacja o ryzyku obecna w treści.", None, 0.6))
    rules.append(
        _rule("2", "pass", "Materiał oznaczony jako marketingowy.", None, 0.6)
        if _AD_MARK.search(text)
        else _rule("2", "fail", "Treść promocyjna bez oznaczenia reklamy.", gain, 0.6)
    )
    rules.append(_rule("4", "unknown", _NOT_RENDERED, None, 0.0))
    rules.append(_rule("6", "unknown", _NOT_RENDERED, None, 0.0))
    past = _quote(text, _PAST)
    if past is None:
        rules.append(_rule("14", "na", "Brak wyników historycznych.", None, 0.6))
    elif _PAST_WARNING.search(text):
        rules.append(_rule("14", "pass", "Ostrzeżenie przy wynikach historycznych.", past, 0.6))
    else:
        rules.append(_rule("14", "fail", "Wyniki historyczne bez ostrzeżenia.", past, 0.6))
    forecast = _quote(text, _FORECAST)
    rules.append(
        _rule("15", "fail", "Obietnica przyszłych wyników.", forecast, 0.6)
        if forecast
        else _rule("15", "na", "Brak prognoz.", None, 0.6)
    )
    return rules


def _m1(text: str) -> list[RuleResult] | None:
    promo = _quote(text, _AFFILIATE)
    if promo is None:
        return None
    marked = _AD_MARK.search(text)
    return [
        _rule("2", "pass", "Reklama oznaczona.", None, 0.6)
        if marked
        else _rule("2", "fail", "Treść promocyjna bez oznaczenia reklamy.", promo, 0.7),
        _rule("3", "pass", "Informacja o ryzyku obecna.", None, 0.5)
        if _RISK.search(text)
        else _rule("3", "fail", "Brak informacji o ryzyku.", promo, 0.6),
    ]


def _m3(text: str) -> list[RuleResult] | None:
    checks = [
        ("76a", _ADVICE_PERSONAL, "Oferta rekomendacji dopasowanej do klienta."),
        ("76c", _ADVICE_BUY, "Wskazanie, co kupić lub sprzedać."),
        ("76e", _ADVICE_MANAGE, "Zarządzanie kapitałem klienta."),
    ]
    rules = []
    for rule_id, pattern, why in checks:
        quote = _quote(text, pattern)
        rules.append(
            _rule(rule_id, "fail", why, quote, 0.6)
            if quote
            else _rule(rule_id, "pass", "Nie wykryto.", None, 0.5)
        )
    return rules if any(r.status == "fail" for r in rules) else None


_EXPLANATIONS: dict[ModuleId, str] = {
    "m1_third_party_ad": "Atrapa AI: treść promuje usługę inwestycyjną (link/kod partnerski).",
    "m2_risk_disclosure": "Atrapa AI: komunikat o zyskach; sprawdzono ekspozycję ryzyka w tekście.",
    "m3_shadow_advisory": "Atrapa AI: treść wygląda na doradztwo inwestycyjne.",
}


def mock_analyze(post: Post, firm_matches: list[FirmMatch]) -> AnalyzeResponse:
    """Return fixture-like findings for `post` using keyword heuristics."""
    text = post.text
    match = firm_matches[0] if firm_matches else None
    now = datetime.now(UTC)
    findings: list[Finding] = []
    detectors = (
        ("m1_third_party_ad", _m1),
        ("m2_risk_disclosure", _m2),
        ("m3_shadow_advisory", _m3),
    )
    for module, detect in detectors:
        rules = detect(text) if text else None
        if rules is None:
            continue
        score = noisy_or(rules)
        quotes = [e.quote for r in rules for e in r.evidence if e.quote]
        findings.append(
            Finding(
                id=uuid.uuid4(),
                post_id=post.id,
                module=module,
                score=score,
                risk_level=risk_level(score),
                explanation=_EXPLANATIONS[module],  # type: ignore[index]
                quotes=list(dict.fromkeys(quotes)),
                firm=match.firm if match else None,
                firm_match=match,
                advertiser=post.author if module != "m2_risk_disclosure" else None,
                rules=rules,
                model=MOCK_MODEL,
                used_llm=False,
                created_at=now,
            )
        )
    return AnalyzeResponse(findings=findings, embedding=None, lang=post.lang, timings_ms={})
