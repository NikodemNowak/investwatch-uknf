"""`/analyze`: route a post to modules M1/M2/M3 and build `Finding`s.

Routing, by who the publisher is:
- M2 (`m2_risk_disclosure`): the post comes from a firm found in the KNF registers (`owner`),
  or is unmatched promotional material (firm unknown). Rules 1-18 of risk_rules.yaml.
- M1 (`m1_third_party_ad`): the post only mentions a registered firm (`mention`), i.e. a
  third-party ad. Score = noisy-OR of the M1 rules, promotion markers and the classifier head.
- M3 (`m3_shadow_advisory`): publisher not in the registers (`not_registered`) and the text
  carries art. 76 UoIF advice elements (or a confident embedding head). Skipped for
  registered firms, which KNF already supervises.
Thresholds and head weights come from `classifier/weights/`; `mock` mode needs no Ollama.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from .classifier.features import extract
from .classifier.model import HeadOutput, load_head, module_thresholds, predict, weights_dir
from .config import AiMode, Settings
from .embed import mock_embedding, try_embed
from .llm import OllamaClient, Usage
from .preprocess import clean_text, detect_lang
from .review import ReviewOutcome, pending_state, review_rules
from .rules import (
    M1_RULE_IDS,
    M2_RULE_IDS,
    M3_ELEMENT_IDS,
    RuleContext,
    evaluate,
    load_rules,
    load_rules_file,
)
from .rules.checks import has_promotional_claim
from .schemas import (
    ContractModel,
    Finding,
    FirmMatch,
    LlmReviewState,
    ModuleId,
    Post,
    Probability,
    RenderSnapshot,
    RuleResult,
)
from .scoring import MEDIUM_BAND, advisory_score, noisy_or, risk_level, rules_score

FINDING_NS = uuid.UUID("6f1c3c1e-5a43-4c55-9d1e-6b8a2f0b7a11")
EMBED_MAX_CHARS = 8000
MAX_QUOTES = 5
MAX_PROMOTED_NAMES = 3
"""A third-party page naming many firms (a ranking) lists this many in the explanation."""

M1_MARKER_WEIGHTS: dict[str, float] = {
    "ad_label": 0.5,
    "affiliate_link": 0.6,
    "referral_phrase": 0.6,
    "promo_code": 0.5,
    "cta": 0.3,
    "bonus": 0.3,
}
"""Promotion markers for M1: p_markers = noisy-OR of the categories present."""
RegisterStatus = Literal["registered", "registered_without_advice", "not_registered"]
OFF_REGISTER_NOTE = "domena spoza rejestru"
M3_GATE = ("advisory_personalised", "advisory_buy_sell", "advisory_management")
"""M3 runs when a core advice element is present (or the embedding head is confident)."""
M3_HEAD_GATE = 0.5
"""Without any art. 76 lexicon hit, the embedding head opens M3 only above this probability:
its training data is half positives, far above the base rate of an arbitrary post."""
M3_LISTING_GATE = ("advisory_buy_sell",)
"""On a page comparing licensed firms, only the publisher's own buy / sell call opens M3."""
READER_ADDRESSED = re.compile(
    r"\b(?:tw(?:ój|oj|oja|oją|oje|ojej|oich|oim|oimi|ojego|ojemu)|you|your|dob(?:ior|ier)\w*)\b",
    re.IGNORECASE,
)
"""...and only advice tailored to the reader (art. 76 element a, addressed to "you" or offered
by the publisher: "dobierzemy") lets it reach the alert level there. A ranking's generic "which
shares to buy" wording, or a listed firm's "osobisty menedżer", is not advice by the page."""
LISTING_MIN_FIRMS = 2
LISTING_NAME_CONFIDENCE = 0.95
"""A content match this sure is the firm's full registered name (backend `CONF_FULL_NAME`),
not a short brand that may be a common word ("Shares", "dealing")."""
ALIAS_CONFIDENCE = 0.9
"""Firm matches at least this sure (alias, domain) keep the M1 head score; fuzzy ones scale it."""
CLEAR_RULES = frozenset({"3", "4", "5", "6", "7", "14", "17", "18"})
"""M2 rules whose failure is unambiguous on its own: no risk warning next to gain claims, a
warning measured as too small / hidden / behind a click, past results without the disclaimer,
the supervisor used as approval or safety. Formal omissions (name, ad label, tax note, forecast
wording) are not in this set."""
CLEAR_CONFIDENCE = 0.75
REGISTERED_NOTE = "Podmiot z rejestru KNF: możliwe naruszenie – do weryfikacji przez analityka."
FICTIONAL_NOTE = (
    "Firma fikcyjna (demo) – udaje wpis w rejestrze KNF: możliwe naruszenie – do weryfikacji"
    " przez analityka."
)
"""A demo firm is not supervised; the explanation must not call it registered."""


class AnalyzeRequest(ContractModel):
    """Body of `POST /analyze`."""

    post: Post
    render: RenderSnapshot | None = None
    firm_matches: list[FirmMatch] = Field(default_factory=list)
    mode: AiMode | None = None
    thresholds: dict[ModuleId, Probability] | None = None
    register_status: RegisterStatus | None = None
    """Is the publisher in the KNF registers (with A5 advice)? None = infer from matches."""
    defer_llm: bool = False
    """With mode `llm`: run rules only and mark findings that need the model `queued`; the
    backend then sends the post again (without `defer_llm`) from its `llm` queue."""
    embed: bool = True
    """False skips the embedding (the LLM pass already has one from the fast pass)."""
    embedding: list[float] | None = None
    """An embedding the caller already has (same model); used by the classifier heads."""
    knf_warning: str | None = None
    """Entity name when the publisher is on the KNF public warning list (matched by the
    backend against `data/registry/knf_warnings.json`): an "unauthorised entity" flag that
    opens an M3 finding and is named in it, but does not raise the advice score (KNF lists
    most such entities for brokerage, not advice; see docs/eval/LABELING.md)."""


class AnalyzeResponse(ContractModel):
    """Response of `POST /analyze`."""

    findings: list[Finding]
    embedding: list[float] | None
    lang: str | None
    timings_ms: dict[str, float]
    chars: int = 0
    """Length of the cleaned text."""
    tokens: int | None = None
    """Input tokens of the embedded text as counted by the embedding model's tokenizer."""
    embed_model: str | None = None
    llm: Usage | None = None
    """Model, token counts and wall time of the LLM review, when one ran."""
    llm_error: str | None = None


class _Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.last = self.t0
        self.ms: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.ms[name] = round((now - self.last) * 1000, 2)
        self.last = now

    def total(self) -> dict[str, float]:
        self.ms["total"] = round((time.perf_counter() - self.t0) * 1000, 2)
        return self.ms


def _quotes(rules: list[RuleResult]) -> list[str]:
    out: list[str] = []
    for r in rules:
        if r.status != "fail":
            continue
        for e in r.evidence:
            if e.quote and e.quote not in out:
                out.append(e.quote)
    return out[:MAX_QUOTES]


def _failed_names(rules: list[RuleResult]) -> str:
    return "; ".join(f"{r.rule_id} {r.name}" for r in rules if r.status == "fail")


def lists_licensed_firms(matches: list[FirmMatch]) -> bool:
    """A comparison or ranking of licensed firms (no publisher, two or more named firms).

    The firms count when named by their full registered names, not by a short brand. Such a
    page describes the listed firms' services (a personal manager, the MiFID survey, managed
    funds): the firms' licensed activities, not advice given by the page. An independent
    comparison is M1's business, not M3's (docs/eval/LABELING.md).
    """
    if any(m.on == "author" for m in matches):
        return False
    named = {
        m.firm.id
        for m in matches
        if m.on == "content"
        and not m.firm.fictional
        and m.method in ("alias", "domain")
        and m.confidence >= LISTING_NAME_CONFIDENCE
    }
    return len(named) >= LISTING_MIN_FIRMS


def informational(score: float, threshold: float) -> float:
    """Cap a score in the `low` band of `threshold`: reported for context, never an alert."""
    floor = threshold - min(MEDIUM_BAND, threshold / 2)
    return min(score, max(0.0, floor - 0.01))


def analyze(
    req: AnalyzeRequest,
    settings: Settings,
    client: OllamaClient | None = None,
    mode: AiMode | None = None,
) -> AnalyzeResponse:
    """Run preprocessing, routing, rules, optional LLM review, scoring and embedding."""
    mode = mode or req.mode or settings.ai_mode
    timer = _Timer()
    post = req.post
    text = clean_text(post.text)
    timer.lap("preprocess")
    if post.fetch_status != "ok" or not text:
        return AnalyzeResponse(findings=[], embedding=None, lang=None, timings_ms=timer.total())

    lang = post.lang or detect_lang(text)
    thresholds = module_thresholds(settings)
    thresholds.update(req.thresholds or {})
    created_at = post.last_seen_at if mode == "mock" else datetime.now(UTC)
    rules_version = load_rules_file().version

    def finding(
        module: ModuleId,
        score: float,
        explanation: str,
        rules: list[RuleResult],
        *,
        quotes: list[str],
        firm_match: FirmMatch | None = None,
        advertiser: str | None = None,
        review: LlmReviewState = "none",
        clf: HeadOutput | None = None,
        cap_medium: bool = False,
    ) -> Finding:
        score = round(min(1.0, max(0.0, score)), 4)
        level = risk_level(score, thresholds[module])
        if cap_medium and level == "high":
            level = "medium"
        used_llm = review == "done"
        model = f"{settings.llm_model}+{rules_version}" if used_llm else rules_version
        if clf is not None:
            model += f"+{clf.version}-{clf.variant}"
        return Finding(
            id=uuid.uuid5(FINDING_NS, f"{post.id}:{module}"),
            post_id=post.id,
            module=module,
            score=score,
            risk_level=level,
            explanation=explanation,
            quotes=quotes,
            firm=firm_match.firm if firm_match else None,
            firm_match=firm_match,
            advertiser=advertiser,
            rules=rules,
            model=f"mock+{model}" if mode == "mock" else model,
            used_llm=used_llm,
            llm_review=review,
            created_at=created_at,
        )

    embedding: list[float] | None = None
    tokens: int | None = None
    embed_model: str | None = None
    if req.embedding is not None:
        embedding, embed_model = req.embedding, settings.embed_model
    elif not req.embed or not settings.embed_enabled:
        pass
    elif mode == "mock":
        embedding, embed_model = mock_embedding(text), "mock"
    else:
        embedding, tokens = try_embed(
            text[:EMBED_MAX_CHARS], client, settings.embed_model, settings.embed_timeout_s
        )
        embed_model = settings.embed_model if embedding is not None else None
    timer.lap("embed")
    # Mock vectors are random: the heads then fall back to their lexicon variant.
    head_embedding = embedding if embed_model not in (None, "mock") else None

    def head(module: ModuleId, rules: list[RuleResult]) -> HeadOutput | None:
        if not settings.classifier or module == "m2_risk_disclosure":
            return None
        weights = load_head(module, weights_dir(settings))
        if weights is None:
            return None
        out = predict(weights, extract(module, ctx, rules), head_embedding)
        timer.lap("classifier")
        return out

    owner = max(
        (m for m in req.firm_matches if m.on == "author"),
        key=lambda m: m.confidence,
        default=None,
    )
    mention = max(
        (m for m in req.firm_matches if m.on == "content"),
        key=lambda m: m.confidence,
        default=None,
    )
    primary = owner or mention
    ctx = RuleContext.build(
        text,
        firm=primary.firm if primary else None,
        render=req.render,
        lang=lang,
    )
    want_llm = mode == "llm" and client is not None
    findings: list[Finding] = []
    llm_runs: list[ReviewOutcome] = []

    def second_opinion(rules: list[RuleResult]) -> ReviewOutcome:
        if not want_llm:
            # Rules-only service: say the model review is unavailable rather than "not needed".
            lite = mode == "rules" and pending_state(rules) == "queued"
            return ReviewOutcome(rules=rules, state="unavailable" if lite else "none")
        if req.defer_llm:
            return ReviewOutcome(rules=rules, state=pending_state(rules))
        assert client is not None
        outcome = review_rules(text, rules, client, settings.llm_model)
        timer.lap("llm")
        llm_runs.append(outcome)
        return outcome

    def m2(firm_match: FirmMatch | None) -> Finding:
        rules = evaluate(ctx, M2_RULE_IDS)
        timer.lap("rules")
        reviewed = second_opinion(rules)
        rules = reviewed.rules
        failed = _failed_names(rules)
        unknown = sum(r.status == "unknown" for r in rules)
        explanation = (f"Naruszenia: {failed}." if failed else "Nie wykryto naruszeń.") + (
            f" Nie oceniono {unknown} reguł." if unknown else ""
        )
        off_register = firm_match is not None and OFF_REGISTER_NOTE in firm_match.matched_text
        if off_register:
            assert firm_match is not None
            explanation += (
                f" Strona przedstawia się jako {firm_match.firm.name}, ale jej domena nie"
                " figuruje w rejestrze KNF (domena spoza rejestru)."
            )
        # A supervised firm's own material: "Wysokie ryzyko" only on unambiguous evidence
        # (ADR 0009); formal omissions stay a possible violation for the analyst.
        supervised = firm_match is not None and firm_match.on == "author" and not off_register
        clear = any(
            r.status == "fail" and r.rule_id in CLEAR_RULES and r.confidence >= CLEAR_CONFIDENCE
            for r in rules
        )
        if supervised and failed:
            assert firm_match is not None
            explanation += " " + (FICTIONAL_NOTE if firm_match.firm.fictional else REGISTERED_NOTE)
        return finding(
            "m2_risk_disclosure",
            rules_score(rules),
            explanation,
            rules,
            quotes=_quotes(rules),
            firm_match=firm_match,
            review=reviewed.state,
            cap_medium=supervised and not clear,
        )

    if owner is not None:
        findings.append(m2(owner))
    elif mention is not None:
        rules = evaluate(ctx, M1_RULE_IDS)
        timer.lap("rules")
        reviewed = second_opinion(rules)
        rules = reviewed.rules
        by_category = {c: ctx.hits(c) for c in M1_MARKER_WEIGHTS if ctx.hits(c)}
        p_markers = noisy_or(M1_MARKER_WEIGHTS[c] for c in by_category)
        # A page repeats its labels ("Advertisement" on every ranking row): list each once.
        unique: dict[str, str] = {}
        for hits in by_category.values():
            for h in hits:
                text = " ".join(h.text.split())
                unique.setdefault(text.casefold(), text)
        markers = list(unique.values())
        statuses = {r.rule_id: r.status for r in rules}
        labelled = {"pass": "oznaczona", "fail": "nieoznaczona"}.get(statuses["2"], "bez cech")
        risk = {"pass": "z ostrzeżeniem o ryzyku", "fail": "bez ostrzeżenia o ryzyku"}.get(
            statuses["3"], "bez twierdzeń o zysku ani o ryzyku"
        )
        promoted = [mention.firm.name] + [
            m.firm.name
            for m in req.firm_matches
            if m.on == "content" and m.firm.id != mention.firm.id
        ]
        promoted = list(dict.fromkeys(promoted))
        named = ", ".join(promoted[:MAX_PROMOTED_NAMES]) + (
            f" i inne firmy (razem {len(promoted)})" if len(promoted) > MAX_PROMOTED_NAMES else ""
        )
        explanation = (
            f"{post.author} promuje {named}"
            + (
                f" (sygnały: {', '.join(markers[:4])})"
                if markers
                else " (brak znaczników promocji)"
            )
            + f"; reklama {labelled}, {risk}."
        )
        clf = head("m1_third_party_ad", rules)
        if clf is None:
            score = mention.confidence * p_markers
        else:
            score = clf.probability * min(1.0, mention.confidence / ALIAS_CONFIDENCE)
            explanation += " " + clf.describe()
        if not by_category:
            # Naming licensed firms (an exchange, an encyclopedia, an editorial) is not an
            # advertisement: without one promotion marker the page stays informational.
            score = informational(score, thresholds["m1_third_party_ad"])
        findings.append(
            finding(
                "m1_third_party_ad",
                score,
                explanation,
                rules,
                quotes=(markers + _quotes(rules))[:MAX_QUOTES],
                firm_match=mention,
                advertiser=post.author,
                review=reviewed.state,
                clf=clf,
            )
        )

    status = req.register_status or ("registered" if owner is not None else "not_registered")
    # M3 is "advice without a licence": only for publishers outside the KNF registers. A
    # registered firm without A5 (a broker, a notified EEA firm) is supervised by KNF and its
    # own material goes through M2 (docs/decisions/0009-fair-treatment-of-real-firms.md).
    if status == "not_registered":
        # On a comparison of licensed firms the advice-like words describe those firms'
        # services; only the page's own buy / sell call (or a KNF warning) opens M3 there.
        listing = lists_licensed_firms(req.firm_matches)
        gated = ctx.has(*(M3_LISTING_GATE if listing else M3_GATE))
        elements = evaluate(ctx, M3_ELEMENT_IDS)
        timer.lap("advisory")
        clf = head("m3_shadow_advisory", elements)
        # Without a lexicon hit only a confident embedding head may open an M3 finding, and
        # never on a listing (the head reads the listed firms' services as advice too).
        if req.knf_warning:
            gated = True
        if not gated and (
            listing
            or clf is None
            or clf.variant != "embedding"
            or clf.probability < max(thresholds["m3_shadow_advisory"], M3_HEAD_GATE)
        ):
            clf = None
        if gated or clf is not None:
            f = load_rules_file()
            metas = load_rules()
            weighted = sum(
                metas[e.rule_id].weight * e.confidence for e in elements if e.status == "fail"
            )
            present = ", ".join(e.rule_id[-1] for e in elements if e.status == "fail") or "brak"
            explanation = (
                f"Elementy doradztwa inwestycyjnego (art. 76 UoIF): {present}. "
                "Podmiot nie występuje w rejestrach KNF jako autor publikacji."
            )
            if clf is None:
                score = advisory_score(weighted, bias=f.advisory_bias, scale=f.advisory_scale)
            else:
                score = clf.probability
                explanation += " " + clf.describe()
            personalised = any(
                READER_ADDRESSED.search(h.text) for h in ctx.hits("advisory_personalised")
            )
            if listing and not personalised and not req.knf_warning:
                score = informational(score, thresholds["m3_shadow_advisory"])
                explanation += (
                    " Strona porównuje licencjonowane firmy, a nie zawiera porady dopasowanej"
                    " do odbiorcy: wynik informacyjny."
                )
            if req.knf_warning:
                explanation += (
                    f" Podmiot figuruje na liście ostrzeżeń publicznych KNF ({req.knf_warning}):"
                    " działalność bez zezwolenia; wynik ocenia wyłącznie treść."
                )
            findings.append(
                finding(
                    "m3_shadow_advisory",
                    score,
                    explanation,
                    elements,
                    quotes=_quotes(elements),
                    advertiser=post.author,
                    clf=clf,
                )
            )

    if owner is None and mention is None and has_promotional_claim(ctx):
        # Unmatched promotional material: still report the M2 checks, firm unknown.
        findings.insert(0, m2(None))

    usage = next((o.usage for o in llm_runs if o.usage is not None), None)
    error = next((o.error for o in llm_runs if o.error), None)
    return AnalyzeResponse(
        findings=findings,
        embedding=embedding,
        lang=lang,
        timings_ms=timer.total(),
        chars=len(text),
        tokens=tokens,
        embed_model=embed_model,
        llm=usage,
        llm_error=error,
    )
