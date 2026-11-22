"""Rule metadata (from YAML), the `@rule` decorator and the evaluation loop."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from ..preprocess import detect_lang, sentences
from ..schemas import CheckType, Evidence, Probability, RegisteredFirm, RenderSnapshot, RuleResult
from ..schemas import RuleStatus as Status

HERE = Path(__file__).resolve().parent
RULES_YAML = HERE / "risk_rules.yaml"
LEXICON_YAML = HERE / "lexicon_pl.yaml"

M2_RULE_IDS: tuple[str, ...] = (
    *(str(i) for i in range(1, 12)),
    "12a",
    "12b",
    *(str(i) for i in range(13, 19)),
)
"""Module 2 rules in report order."""
M1_RULE_IDS: tuple[str, ...] = ("2", "3", "14", "15", "17", "18")
"""Subset of M2 rules reported for third-party ads (module 1)."""
M3_ELEMENT_IDS: tuple[str, ...] = ("76a", "76b", "76c", "76d", "76e")
"""Art. 76 UoIF elements; status "fail" means the element is present."""


class RuleMeta(BaseModel):
    """One rule as declared in `risk_rules.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    legal_basis: str
    type: CheckType
    weight: Probability
    description: str = ""


class RulesFile(BaseModel):
    """Shape of `risk_rules.yaml`."""

    model_config = ConfigDict(extra="forbid")

    version: str
    rules: list[RuleMeta]
    advisory_elements: list[RuleMeta]
    advisory_bias: float
    advisory_scale: float


@cache
def load_rules_file() -> RulesFile:
    """Parse and validate `risk_rules.yaml` once."""
    return RulesFile.model_validate(yaml.safe_load(RULES_YAML.read_text(encoding="utf-8")))


def load_rules() -> dict[str, RuleMeta]:
    """All rules (M2 and art. 76 elements) keyed by id."""
    f = load_rules_file()
    return {r.id: r for r in (*f.rules, *f.advisory_elements)}


@cache
def load_lexicon() -> dict[str, tuple[re.Pattern[str], ...]]:
    """Compile `lexicon_pl.yaml` once: category -> case-insensitive patterns."""
    raw = yaml.safe_load(LEXICON_YAML.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("lexicon must be a mapping")
    out: dict[str, tuple[re.Pattern[str], ...]] = {}
    for category, patterns in raw.items():
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            raise ValueError(f"lexicon category {category!r} must be a list of strings")
        out[str(category)] = tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    return out


@dataclass(frozen=True)
class Hit:
    """One lexicon match."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Outcome:
    """What a rule function returns; the registry adds the metadata."""

    status: Status
    confidence: float
    explanation: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule may look at, with lazily computed lexicon hits."""

    text: str
    firm: RegisteredFirm | None = None
    render: RenderSnapshot | None = None
    lang_hint: str | None = None

    @classmethod
    def build(
        cls,
        text: str,
        *,
        firm: RegisteredFirm | None = None,
        render: RenderSnapshot | None = None,
        lang: str | None = None,
    ) -> RuleContext:
        """Create a context for already-cleaned text."""
        return cls(text=text, firm=firm, render=render, lang_hint=lang)

    @cached_property
    def lang(self) -> str | None:
        """Language of the whole text (hint from the collector wins)."""
        return self.lang_hint or detect_lang(self.text)

    @cached_property
    def sentence_spans(self) -> list[tuple[int, int]]:
        """Sentence boundaries of the text."""
        return sentences(self.text)

    @cached_property
    def _hits(self) -> dict[str, list[Hit]]:
        return {}

    def hits(self, category: str) -> list[Hit]:
        """Non-overlapping lexicon matches of one category, sorted by position."""
        cached = self._hits.get(category)
        if cached is not None:
            return cached
        found: list[Hit] = []
        for pattern in load_lexicon()[category]:
            found.extend(Hit(m.start(), m.end(), m.group()) for m in pattern.finditer(self.text))
        found.sort(key=lambda h: (h.start, -h.end))
        merged: list[Hit] = []
        for h in found:
            if merged and h.start < merged[-1].end:
                continue
            merged.append(h)
        self._hits[category] = merged
        return merged

    @cached_property
    def body(self) -> RuleContext:
        """The same context without navigation, buttons, repeated lines and footer boilerplate.

        Rules about promotional claims (2, 3, 15, 16) read this view: on real firm pages the
        menu ("Otwórz konto", "Zyski") and the footer are not the advertisement's content.
        """
        text = content_text(self.text)
        if text == self.text:
            return self
        return RuleContext(text=text, firm=self.firm, render=self.render, lang_hint=self.lang)

    @cached_property
    def unboilerplated(self) -> RuleContext:
        """The text without footer, cookie and privacy-notice lines; headings and menus stay.

        The art. 76 elements read this view: an offer's headings ("Sygnały kupna",
        "Indywidualny opiekun") matter, a cookie banner ("dopasowana do Twoich potrzeb") not.
        """
        lines = [line for line in self.text.splitlines() if not _FOOTER.search(line)]
        text = "\n".join(lines)
        if text == self.text:
            return self
        return RuleContext(text=text, firm=self.firm, render=self.render, lang_hint=self.lang)

    @cached_property
    def _body_lines(self) -> frozenset[str]:
        return frozenset(self.body.text.splitlines())

    def in_body(self, hit: Hit) -> bool:
        """True when the line holding `hit` is content (kept by `body`), not a menu or footer."""
        start = self.text.rfind("\n", 0, hit.start) + 1
        end = self.text.find("\n", hit.end)
        return self.text[start : end if end >= 0 else None].strip() in self._body_lines

    def has(self, *categories: str) -> bool:
        """True when any of the categories matches."""
        return any(self.hits(c) for c in categories)

    def sentence_of(self, hit: Hit, max_len: int = 240) -> str:
        """The sentence containing `hit`, trimmed around it when too long."""
        for a, b in self.sentence_spans:
            if a <= hit.start < b:
                if b - a > max_len:
                    a = max(a, hit.start - max_len // 2)
                    b = min(b, a + max_len)
                return self.text[a:b].strip()
        return hit.text


_KEEP_SHORT = re.compile(
    r"#|%|reklam|marketing|sponsor|współprac|partner|ryzyk|risk|advert|\bad\b",
    re.IGNORECASE,
)
_FOOTER = re.compile(
    r"©|\bcookie|polityk\w* prywatności|wszelkie prawa zastrzeżone|all rights reserved"
    r"|regulamin serwisu|mapa strony"
    # Privacy notices and consent checkboxes (RODO) under contact forms.
    r"|danych osobowych|dane osobowe|\bRODO\b|reCAPTCHA|wyrażam zgodę",
    re.IGNORECASE,
)
BODY_MIN_WORDS = 5


def content_text(text: str) -> str:
    """Drop menu items, buttons, duplicated lines and footer lines; keep sentences.

    A line stays when it reads like content: at least five words, sentence punctuation, or a
    marker that matters on its own line (hashtags, a percentage, an ad / risk label).
    """
    seen: set[str] = set()
    kept: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or _FOOTER.search(s):
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        words = len(s.split())
        if words >= BODY_MIN_WORDS or s[-1] in ".!?:;" or _KEEP_SHORT.search(s):
            kept.append(s)
    return "\n".join(kept)


RuleFn = Callable[[RuleContext], Outcome]
_REGISTRY: dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    """Register a check function for `rule_id` (must exist in `risk_rules.yaml`)."""

    def decorator(fn: RuleFn) -> RuleFn:
        if rule_id in _REGISTRY:
            raise ValueError(f"rule {rule_id} registered twice")
        if rule_id not in load_rules():
            raise ValueError(f"rule {rule_id} missing from {RULES_YAML.name}")
        _REGISTRY[rule_id] = fn
        return fn

    return decorator


def registered() -> frozenset[str]:
    """Ids with an implementation."""
    return frozenset(_REGISTRY)


def evidence(quote: str | None, **measurements: float | str) -> Evidence:
    """Text-only evidence (no viewport or bbox)."""
    return Evidence(quote=quote, viewport=None, bbox=None, measurements=dict(measurements))


def to_result(meta: RuleMeta, outcome: Outcome) -> RuleResult:
    """Combine YAML metadata with a rule outcome."""
    return RuleResult(
        rule_id=meta.id,
        name=meta.name,
        status=outcome.status,
        confidence=round(min(1.0, max(0.0, outcome.confidence)), 3),
        check_type=meta.type,
        weight=meta.weight,
        explanation=outcome.explanation,
        legal_basis=meta.legal_basis,
        evidence=outcome.evidence,
    )


NOT_IMPLEMENTED = Outcome("unknown", 0.0, "Reguła nie jest jeszcze zaimplementowana.")


def evaluate(ctx: RuleContext, rule_ids: Iterable[str] = M2_RULE_IDS) -> list[RuleResult]:
    """Run the given rules in order; rules without an implementation report `unknown`."""
    metas = load_rules()
    results: list[RuleResult] = []
    for rid in rule_ids:
        fn = _REGISTRY.get(rid)
        results.append(to_result(metas[rid], fn(ctx) if fn else NOT_IMPLEMENTED))
    return results
