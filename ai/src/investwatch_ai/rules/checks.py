"""Text checks for the M2 rules and art. 76 elements.

Each function sees cleaned text; render rules (4-8, 13) delegate to `render_checks` and LLM rules
(9, 11, 12a) need the model. Without their input they report `unknown` when applicable, `na`
otherwise.
"""

from __future__ import annotations

import itertools
import re

from rapidfuzz import fuzz

from ..preprocess import detect_lang
from ..schemas import RenderSnapshot
from . import render_checks
from .registry import Hit, Outcome, RuleContext, evidence, rule

PROMO_CATEGORIES = (
    "ad_label",
    "cta",
    "affiliate_link",
    "referral_phrase",
    "promo_code",
    "bonus",
    "promo_offer",
    "gains_claim",
)
GAIN_SHARE_PROMO = 0.15
"""Share of sentences with gain claims that makes a text promotional without other cues."""
SUPERVISOR_SAFETY_WINDOW = 80
"""Max characters between a supervisor mention and a safety claim for rule 18."""
_NON_INVESTMENT_SAFETY = re.compile(
    r"\b(?:dan\w*|logowani\w*|haseł|hasło|szyfrow\w*|uwierzytelni\w*|połączeni\w*|SSL|"
    r"płatnoś\w*|przelew\w*|aplikacj\w*|serwis\w*|stron\w* internetow\w*|cookies)\b",
    re.IGNORECASE,
)
"""Safety claims about data, logins or payments, not about the investment (rule 18)."""
_ADVICE_NEGATION = re.compile(
    r"\bnie (?:stanowi\w*|jest|są|udzielam\w*|świadczym\w*|oferujem\w*|daj\w*)"
    r"(?:\s+\w+){0,2}\s*$",
    re.IGNORECASE,
)
"""Text right before an advice phrase that negates it ("nie stanowi rekomendacji zakupu")."""
_NEGATED_BEFORE = re.compile(r"\b(?:nie|ani|bez)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
"""A safety word under negation ("nie ma gwarancji", "nie chroni") is a warning, not a claim."""
_YEAR_RANGE = re.compile(
    r"(?<!\d)(?:\d{1,2}[./])?((?:19|20)\d\d)\s*[-–—]\s*(?:\d{1,2}[./])?((?:19|20)\d\d)(?!\d)"
)
"""A period written as a range ("2021–2025", "01.2021–12.2025"): every year in it counts."""
_YEAR = re.compile(r"(?<!\d)(?:19[89]\d|20[0-4]\d)(?!\d)")
_SINCE_INCEPTION = re.compile(
    r"\bod (?:początku|utworzenia|startu|uruchomienia|debiutu|powstania) (?:\w+ ){0,2}"
    r"|\bod daty (?:utworzenia|uruchomienia)",
    re.IGNORECASE,
)
_SHORT_PERIOD = re.compile(
    r"\b(?:w|za|przez) (?:ciągu )?(?:ostatni\w* )?(?:(?:[1-9]|1[01]) )?"
    r"(?:dni|dzień|tydzień|tygodni\w*|miesiąc\w*|miesięc\w*|kwartał\w*|półrocz\w*)\b"
    r"|\bw (?:styczni|lut|marc|kwietni|maj|czerwc|lipc|sierpni|wrześni|październik|listopad|"
    r"grudni)\w*",
    re.IGNORECASE,
)
FULL_HISTORY_YEARS = 5
"""Art. 44(4)(b): past performance covers the preceding five years (or the whole history)."""

_BRANCH_SUFFIX = re.compile(r"\s+Oddział w Polsce$", re.IGNORECASE)


_LEGAL_FORMS_WRITTEN = (
    (re.compile(r"\s+S\.\s?A\.?$", re.IGNORECASE), r"(?:S\.\s?A\.?|Spółk\w+ Akcyjn\w+)"),
    (
        re.compile(r"\s+sp\.\s?z\s?o\.\s?o\.?$", re.IGNORECASE),
        r"(?:sp\.\s?z\s?o\.\s?o\.?|spółk\w+ z ograniczoną odpowiedzialnością)",
    ),
)
"""Legal forms that a page may write out in full ("Spółka Akcyjna" for "S.A.")."""


def _name_pattern(name: str) -> re.Pattern[str]:
    """Regex for an official name that tolerates Polish inflection ("Banku Inwestycyjnego").

    The legal form may be abbreviated or written out ("S.A." / "Spółka Akcyjna").
    """
    name = _BRANCH_SUFFIX.sub("", name)
    legal = ""
    for suffix, written in _LEGAL_FORMS_WRITTEN:
        if suffix.search(name):
            name, legal = suffix.sub("", name), written
            break
    parts: list[str] = []
    for token in name.split():
        if re.fullmatch(r"[^\W\d_]+", token):
            stem = token[:-2] if len(token) >= 6 else token
            parts.append(re.escape(stem) + r"\w{0,6}")
        else:
            # "MICHAEL/STRÖM" also matches "Michael / Ström" (separators with spaces).
            pieces = re.split(r"\s*[/&-]\s*", token)
            parts.append(r"\s*[/&-]\s*".join(re.escape(p) for p in pieces))
    if legal:
        parts.append(legal)
    return re.compile(r"(?<!\w)" + r"\s+".join(parts), re.IGNORECASE)


def _nearest(a: list[Hit], b: list[Hit]) -> tuple[Hit, Hit, int] | None:
    """Closest pair (gap in characters between the spans) of hits from two lists."""
    best: tuple[Hit, Hit, int] | None = None
    for x in a:
        for y in b:
            gap = max(0, max(x.start, y.start) - min(x.end, y.end))
            if best is None or gap < best[2]:
                best = (x, y, gap)
    return best


def _fmt(hits: list[Hit], limit: int = 3) -> str:
    """Quote up to `limit` distinct cues ("ETFs" repeated on a page is listed once)."""
    unique: dict[str, str] = {}
    for h in hits:
        text = " ".join(h.text.split())
        unique.setdefault(text.casefold(), text)
    return ", ".join(f"„{t}”" for t in list(unique.values())[:limit])


def _years_pl(n: int) -> str:
    """Polish plural of consecutive years: "1 rok", "3 kolejne lata", "5 kolejnych lat"."""
    if n == 1:
        return "1 rok"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} kolejne lata"
    return f"{n} kolejnych lat"


@rule("1")
def firm_identification(ctx: RuleContext) -> Outcome:
    """Official firm name (with legal form) appears in the material."""
    if ctx.firm is not None:
        m = _name_pattern(ctx.firm.name).search(ctx.text)
        if m:
            return Outcome(
                "pass",
                0.9,
                f"Materiał podaje oficjalną nazwę firmy ({ctx.firm.name}).",
                [evidence(m.group())],
            )
        alias = next(
            (
                a
                for a in ctx.firm.aliases
                if fuzz.partial_ratio(a.casefold(), ctx.text.casefold()) >= 95
            ),
            None,
        )
        if alias:
            return Outcome(
                "fail",
                0.75,
                f"Materiał używa nazwy handlowej „{alias}”, ale nie podaje oficjalnej nazwy "
                f"firmy ({ctx.firm.name}).",
                [evidence(alias)],
            )
        return Outcome("fail", 0.7, f"Brak oficjalnej nazwy firmy ({ctx.firm.name}).")
    legal = ctx.hits("legal_form")
    if legal:
        return Outcome(
            "pass",
            0.5,
            "Materiał zawiera nazwę podmiotu z formą prawną (firma nie została dopasowana do "
            "rejestru).",
            [evidence(ctx.sentence_of(legal[0]))],
        )
    return Outcome("fail", 0.5, "Nie znaleziono nazwy podmiotu z formą prawną.")


@rule("2")
def ad_label(ctx: RuleContext) -> Outcome:
    """Promotional material is labelled as an advertisement."""
    ctx = ctx.body
    labels = ctx.hits("ad_label")
    if labels:
        return Outcome(
            "pass",
            0.9,
            f"Materiał jest oznaczony jako reklama: {_fmt(labels)}.",
            [evidence(labels[0].text)],
        )
    strong = [h for c in PROMO_CATEGORIES[1:] if c != "gains_claim" for h in ctx.hits(c)]
    # "Inflacja zmniejsza realny zysk" in a risk description is not a promise of gains.
    gains = [h for h in ctx.hits("gains_claim") if not _RISK_WORD.search(ctx.sentence_of(h))]
    spans = ctx.sentence_spans
    gain_share = len({i for i, (a, b) in enumerate(spans) for h in gains if a <= h.start < b}) / (
        max(1, len(spans))
    )
    # Gain words alone ("zyski z inwestycji") are product description on a long page; they
    # make it promotional only when they dominate the text.
    promo = strong + (gains if strong or gain_share >= GAIN_SHARE_PROMO else [])
    if promo:
        # Quote the most telling cue (a code or an offer before a bare "kliknij"), then the first.
        rank = {id(h): i for i, c in enumerate(_PROMO_EVIDENCE_ORDER) for h in ctx.hits(c)}
        promo.sort(key=lambda h: (rank.get(id(h), len(_PROMO_EVIDENCE_ORDER)), h.start))
        return Outcome(
            "fail",
            0.6,
            f"Materiał ma charakter promocyjny ({_fmt(promo)}), ale nie jest oznaczony jako "
            "reklama ani materiał marketingowy.",
            [evidence(ctx.sentence_of(promo[0]))],
        )
    return Outcome("na", 0.6, "Nie wykryto cech materiału promocyjnego.")


_RISK_WORD = re.compile(r"\bryzyk\w*", re.IGNORECASE)
_PROMO_EVIDENCE_ORDER = (
    "promo_code",
    "bonus",
    "promo_offer",
    "affiliate_link",
    "referral_phrase",
    "cta",
    "gains_claim",
)
_TAX_WORD = re.compile(r"\bpodat\w*", re.IGNORECASE)
_FIGURE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|proc|zł|PLN|EUR|USD|x\b)", re.IGNORECASE)


def _gain_claims(ctx: RuleContext) -> list[Hit]:
    """Gain phrases that make a claim: with a figure in the sentence, or dominating the text."""
    gains = ctx.hits("gains_claim")
    spans = ctx.sentence_spans
    share = len({i for i, (a, b) in enumerate(spans) for h in gains if a <= h.start < b}) / max(
        1, len(spans)
    )
    # "Podatek od zysków ... 19%" states a tax rate, not a promised gain (rule 16 covers tax).
    gains = [h for h in gains if not _TAX_WORD.search(ctx.sentence_of(h))]
    if share >= GAIN_SHARE_PROMO:
        return gains
    return [h for h in gains if _FIGURE.search(ctx.sentence_of(h, max_len=400))]


def has_promotional_claim(ctx: RuleContext) -> bool:
    """A promotion marker (code, offer, CTA, ...) or a gain claim with a figure ("30% rocznie").

    A bare gain word in navigation ("Średnia ważona stopa zwrotu OFE" on a regulator's menu)
    is not a promotional claim; it does not make a page without any firm an advertisement.
    """
    if any(ctx.hits(c) for c in PROMO_CATEGORIES if c != "gains_claim"):
        return True
    gains = [h for h in ctx.hits("gains_claim") if not _TAX_WORD.search(ctx.sentence_of(h))]
    return any(_FIGURE.search(ctx.sentence_of(h, max_len=400)) for h in gains)


@rule("3")
def gains_with_risk(ctx: RuleContext) -> Outcome:
    """Claims about gains are accompanied by a risk warning."""
    full, ctx = ctx, ctx.body
    gains = _gain_claims(ctx)
    if not gains:
        return Outcome("na", 0.7, "Nie wykryto twierdzeń o zyskach.")
    risks = full.hits("risk_warning")
    if risks and not ctx.hits("risk_warning"):
        ctx = full
        gains = full.hits("gains_claim")
    if not risks:
        return Outcome(
            "fail",
            0.85,
            f"Twierdzenia o zyskach ({_fmt(gains)}) bez żadnej informacji o ryzyku.",
            [evidence(ctx.sentence_of(gains[0]))],
        )
    pair = _nearest(gains, risks)
    assert pair is not None
    return Outcome(
        "pass",
        0.6,
        "Twierdzeniom o zyskach towarzyszy informacja o ryzyku; proporcjonalność i ekspozycję "
        "oceniają reguły renderu i LLM.",
        [evidence(ctx.sentence_of(pair[1]), gap_chars=pair[2])],
    )


def _render_gate(ctx: RuleContext, *, applicable: bool, condition: str) -> Outcome | None:
    """Common `na` / `unknown` outcomes of the render rules; None means "go and measure"."""
    if not applicable:
        return Outcome("na", 0.6, f"Nie dotyczy: {condition}.")
    if ctx.render is None:
        return Outcome("unknown", 0.0, "Brak zrzutu renderu strony (RenderSnapshot).")
    return None


def _has_risk(ctx: RuleContext) -> bool:
    return ctx.has("risk_warning") or (
        ctx.render is not None and render_checks.has_risk_block(ctx.render)
    )


@rule("4")
def risk_font_size(ctx: RuleContext) -> Outcome:
    """Render: risk font vs dominant font."""
    gate = _render_gate(ctx, applicable=_has_risk(ctx), condition="brak bloku ryzyka")
    return gate or render_checks.font_size(_render(ctx))


@rule("5")
def risk_contrast(ctx: RuleContext) -> Outcome:
    """Render: contrast, occlusion, opacity of the risk block."""
    gate = _render_gate(ctx, applicable=_has_risk(ctx), condition="brak bloku ryzyka")
    return gate or render_checks.exposure(_render(ctx))


@rule("6")
def risk_hidden(ctx: RuleContext) -> Outcome:
    """Render: risk block only in footer / footnotes / low on the page."""
    if ctx.has("gains_claim") and not _has_risk(ctx):
        return Outcome("na", 0.6, "Nie dotyczy: brak ostrzeżenia o ryzyku (zob. reguła 3).")
    gate = _render_gate(ctx, applicable=ctx.has("gains_claim"), condition="brak twierdzeń o zysku")
    return gate or render_checks.hidden_low(_render(ctx))


@rule("7")
def risk_one_click(ctx: RuleContext) -> Outcome:
    """Render: risk visible without expanding or clicking."""
    gate = _render_gate(ctx, applicable=ctx.has("gains_claim"), condition="brak twierdzeń o zysku")
    return gate or render_checks.one_click(_render(ctx))


@rule("8")
def risk_responsive(ctx: RuleContext) -> Outcome:
    """Render: risk block readable in all three viewports."""
    gate = _render_gate(ctx, applicable=_has_risk(ctx), condition="brak bloku ryzyka")
    return gate or render_checks.responsive(_render(ctx))


def _render(ctx: RuleContext) -> RenderSnapshot:
    assert ctx.render is not None  # guaranteed by _render_gate
    return ctx.render


@rule("9")
def risk_clarity(ctx: RuleContext) -> Outcome:
    """LLM: warning is understandable for a retail client."""
    if not ctx.has("risk_warning"):
        return Outcome("na", 0.6, "Nie dotyczy: brak ostrzeżenia o ryzyku.")
    return Outcome("unknown", 0.0, "Zrozumiałość ostrzeżenia wymaga oceny modelu językowego.")


@rule("10")
def language_consistency(ctx: RuleContext) -> Outcome:
    """Risk warning in the same language as the main message."""
    risks = ctx.hits("risk_warning")
    if not risks:
        return Outcome("na", 0.6, "Nie dotyczy: brak ostrzeżenia o ryzyku.")
    risk_spans = {(a, b) for a, b in ctx.sentence_spans for h in risks if a <= h.start < b}
    risk_text = " ".join(ctx.text[a:b] for a, b in sorted(risk_spans))
    rest = " ".join(ctx.text[a:b] for a, b in ctx.sentence_spans if (a, b) not in risk_spans)
    risk_lang = detect_lang(risk_text)
    main_lang = detect_lang(rest) if rest.strip() else ctx.lang
    if risk_lang is None or main_lang is None:
        return Outcome("unknown", 0.0, "Nie udało się rozpoznać języka ostrzeżenia lub treści.")
    measurements: dict[str, float | str] = {"risk_lang": risk_lang, "main_lang": main_lang}
    if risk_lang != main_lang:
        return Outcome(
            "fail",
            0.8,
            f"Ostrzeżenie o ryzyku jest w innym języku ({risk_lang}) niż główny przekaz "
            f"({main_lang}).",
            [evidence(ctx.sentence_of(risks[0]), **measurements)],
        )
    return Outcome(
        "pass",
        0.8,
        "Ostrzeżenie jest w tym samym języku co treść.",
        [evidence(None, **measurements)],
    )


@rule("11")
def comparisons(ctx: RuleContext) -> Outcome:
    """LLM: comparisons state source and assumptions."""
    hits = ctx.hits("comparison")
    if not hits:
        return Outcome("na", 0.5, "Nie wykryto porównań produktów lub usług.")
    return Outcome(
        "unknown",
        0.0,
        f"Wykryto porównanie ({_fmt(hits)}); ocena źródła i założeń wymaga modelu językowego.",
        [evidence(ctx.sentence_of(hits[0]))],
    )


def _performance_years(ctx: RuleContext, hits: list[Hit], window: int = 600) -> set[int]:
    """Calendar years quoted near the past-performance claims."""
    years: set[int] = set()
    for h in hits:
        a, b = max(0, h.start - window), min(len(ctx.text), h.end + window)
        years.update(int(y) for y in _YEAR.findall(ctx.text[a:b]))
        for m in _YEAR_RANGE.finditer(ctx.text[a:b]):
            lo, hi = int(m.group(1)), int(m.group(2))
            if 0 < hi - lo <= 30:
                years.update(range(lo, hi + 1))
    return years


@rule("12a")
def past_performance_period(ctx: RuleContext) -> Outcome:
    """Past performance covers 5 full 12-month periods (or the whole history), with a period.

    Text heuristic: count the calendar years shown next to the results. Five or more
    consecutive years pass; a shorter series without a "since inception" note, or a result
    for a period shorter than 12 months, fails. Anything else is left to the LLM.
    """
    hits = ctx.hits("past_performance")
    if not hits:
        return Outcome("na", 0.6, "Nie wykryto wyników historycznych.")
    quote = ctx.sentence_of(hits[0])
    years = _performance_years(ctx, hits)
    if years:
        longest = run = 1
        ordered = sorted(years)
        for prev, cur in itertools.pairwise(ordered):
            run = run + 1 if cur == prev + 1 else 1
            longest = max(longest, run)
        shown = ", ".join(str(y) for y in ordered[-6:])
        if longest >= FULL_HISTORY_YEARS:
            return Outcome(
                "pass",
                0.6,
                f"Wyniki historyczne obejmują {longest} kolejnych lat ({shown}).",
                [evidence(quote, years=float(longest))],
            )
        if not _SINCE_INCEPTION.search(ctx.text):
            return Outcome(
                "fail",
                0.6,
                f"Wyniki historyczne obejmują najwyżej {_years_pl(longest)} ({shown}), a nie"
                " ostatnie 5 pełnych lat ani okres od początku działalności.",
                [evidence(quote, years=float(longest))],
            )
    short = next(
        (m for h in hits for m in _SHORT_PERIOD.finditer(ctx.sentence_of(h, max_len=400))), None
    )
    if short is not None and not years:
        return Outcome(
            "fail",
            0.55,
            f"Wynik podano za okres krótszy niż 12 miesięcy („{short.group()}”).",
            [evidence(quote)],
        )
    return Outcome(
        "unknown",
        0.0,
        "Wykryto wyniki historyczne; ocena okresu i źródła wymaga modelu językowego.",
        [evidence(quote)],
    )


@rule("12b")
def past_performance_costs(ctx: RuleContext) -> Outcome:
    """Past performance states the effect of fees (and currency, when relevant)."""
    hits = ctx.hits("past_performance")
    if not hits:
        return Outcome("na", 0.6, "Nie wykryto wyników historycznych.")
    fees = ctx.hits("fees_warning")
    if fees:
        return Outcome(
            "pass",
            0.5,
            "Podano informację o wpływie prowizji i opłat na wyniki.",
            [evidence(ctx.sentence_of(fees[0]))],
        )
    return Outcome(
        "fail",
        0.5,
        "Przy wynikach historycznych brak informacji o wpływie prowizji, opłat i kursów walut.",
        [evidence(ctx.sentence_of(hits[0]))],
    )


@rule("13")
def past_performance_dominance(ctx: RuleContext) -> Outcome:
    """Render: past performance is not the most prominent element."""
    gate = _render_gate(
        ctx, applicable=ctx.has("past_performance"), condition="brak wyników historycznych"
    )
    return gate or render_checks.past_performance_dominance(_render(ctx))


@rule("14")
def past_performance_disclaimer(ctx: RuleContext) -> Outcome:
    """Past performance carries the "not a reliable indicator" disclaimer."""
    hits = ctx.hits("past_performance")
    if not hits:
        return Outcome("na", 0.7, "Nie wykryto wyników historycznych.")
    disclaimers = ctx.hits("past_performance_disclaimer")
    if disclaimers:
        return Outcome(
            "pass",
            0.85,
            "Wyniki historyczne mają zastrzeżenie o braku gwarancji na przyszłość.",
            [evidence(ctx.sentence_of(disclaimers[0]))],
        )
    return Outcome(
        "fail",
        0.8,
        f"Wyniki historyczne ({_fmt(hits)}) bez zastrzeżenia, że nie są wiarygodnym wskaźnikiem "
        "przyszłych wyników.",
        [evidence(ctx.sentence_of(hits[0]))],
    )


def _forecast_hits(ctx: RuleContext) -> list[Hit]:
    """Forecasts of investment results, without contract terms, coupons or disclaimers.

    Strong phrases ("zarobisz 20%") always count; weak ones ("prognoza", "przewiduje") only
    with a return or price figure in the same sentence. A phrase inside an exclusion context
    (a coupon rate, "regulamin przewiduje") or inside the disclaimer itself is dropped.
    """
    excluded = ctx.hits("forecast_exclusion") + ctx.hits("forecast_disclaimer")
    targets = ctx.hits("forecast_target")

    def free(h: Hit) -> bool:
        return not any(e.start <= h.start < e.end or h.start <= e.start < h.end for e in excluded)

    def sentence(h: Hit) -> tuple[int, int]:
        return next(((a, b) for a, b in ctx.sentence_spans if a <= h.start < b), (h.start, h.end))

    out = [h for h in ctx.hits("forecast") if free(h)]
    for h in ctx.hits("forecast_weak"):
        if not free(h):
            continue
        a, b = sentence(h)
        if any(a <= t.start < b and not (h.start <= t.start < h.end) for t in targets):
            out.append(h)
    out.sort(key=lambda h: h.start)
    return out


@rule("15")
def forecasts(ctx: RuleContext) -> Outcome:
    """Forecasts carry a disclaimer; every forecast is flagged in the explanation."""
    # Exclusions read the whole text (a heading "Oprocentowanie wolnych środków" is context),
    # the forecasts themselves only the content lines.
    hits = [h for h in _forecast_hits(ctx) if ctx.in_body(h)]
    if not hits:
        return Outcome("na", 0.6, "Nie wykryto prognoz przyszłych wyników.")
    disclaimers = ctx.hits("forecast_disclaimer")
    if disclaimers:
        return Outcome(
            "pass",
            0.8,
            f"Wykryto prognozę ({_fmt(hits)}) z zastrzeżeniem o braku wiarygodności.",
            [evidence(ctx.sentence_of(hits[0])), evidence(ctx.sentence_of(disclaimers[0]))],
        )
    return Outcome(
        "fail",
        0.8,
        f"Wykryto prognozę przyszłych wyników ({_fmt(hits)}) bez zastrzeżenia, że nie jest "
        "wiarygodnym wskaźnikiem.",
        [evidence(ctx.sentence_of(hits[0]))],
    )


@rule("16")
def tax_information(ctx: RuleContext) -> Outcome:
    """Tax claims say they depend on the client's situation and may change."""
    ctx = ctx.body
    hits = ctx.hits("tax_mention")
    if not hits:
        return Outcome("na", 0.7, "Materiał nie odwołuje się do kwestii podatkowych.")
    missing = []
    if not ctx.has("tax_disclaimer_individual"):
        missing.append("zależności od indywidualnej sytuacji klienta")
    if not ctx.has("tax_disclaimer_change"):
        missing.append("możliwości zmian")
    if not missing:
        return Outcome(
            "pass",
            0.8,
            "Informacja podatkowa zawiera wymagane zastrzeżenia.",
            [evidence(ctx.sentence_of(hits[0]))],
        )
    return Outcome(
        "fail",
        0.8 if len(missing) == 2 else 0.6,
        f"Odwołanie do podatków ({_fmt(hits)}) bez informacji o {' ani '.join(missing)}.",
        [evidence(ctx.sentence_of(hits[0]))],
    )


@rule("17")
def supervisor_approval(ctx: RuleContext) -> Outcome:
    """Supervisor mention does not suggest approval of the product."""
    if not ctx.has("supervisor_mention"):
        return Outcome("na", 0.8, "Brak odwołań do KNF lub innego organu nadzoru.")
    approvals = ctx.hits("supervisor_approval")
    if approvals:
        return Outcome(
            "fail",
            0.85,
            f"Odwołanie do organu nadzoru sugeruje zatwierdzenie produktu: {_fmt(approvals)}.",
            [evidence(ctx.sentence_of(approvals[0]))],
        )
    return Outcome(
        "pass", 0.6, "Wzmianka o nadzorze ma charakter informacyjny (brak sugestii aprobaty)."
    )


@rule("18")
def supervisor_as_safety(ctx: RuleContext) -> Outcome:
    """Supervisor mention is not used as an argument that the investment is safe."""
    mentions = ctx.hits("supervisor_mention") + ctx.hits("supervisor_approval")
    if not mentions:
        return Outcome("na", 0.8, "Brak odwołań do KNF lub innego organu nadzoru.")
    claims = [
        h
        for h in ctx.hits("safety_claim")
        if not _NON_INVESTMENT_SAFETY.search(ctx.sentence_of(h))
        and not _NEGATED_BEFORE.search(ctx.text[max(0, h.start - 30) : h.start])
        and not ctx.sentence_of(h).rstrip().endswith("?")
    ]
    pair = _nearest(mentions, claims)
    if pair is not None and pair[2] <= SUPERVISOR_SAFETY_WINDOW:
        a, b, gap = pair
        quote = ctx.text[min(a.start, b.start) : max(a.end, b.end)]
        return Outcome(
            "fail",
            0.8,
            f"Nadzór („{a.text}”) użyty jako argument bezpieczeństwa („{b.text}”).",
            [evidence(quote, gap_chars=gap)],
        )
    return Outcome(
        "pass", 0.6, "Wzmianka o nadzorze nie jest powiązana z obietnicą bezpieczeństwa."
    )


def _element(ctx: RuleContext, category: str, label: str) -> Outcome:
    # Cookie banners and footers ("dopasowana do Twoich potrzeb") are not an offer.
    ctx = ctx.unboilerplated
    hits = [h for h in ctx.hits(category) if not _ADVICE_NEGATION.search(ctx.text[: h.start])]
    if hits:
        return Outcome(
            "fail",
            0.8,
            f"Element obecny: {label} ({_fmt(hits)}).",
            [evidence(ctx.sentence_of(h)) for h in hits[:2]],
        )
    return Outcome("pass", 0.6, f"Nie wykryto: {label}.")


@rule("76a")
def advisory_personalised(ctx: RuleContext) -> Outcome:
    """Art. 76 a: personalised recommendation."""
    return _element(ctx, "advisory_personalised", "rekomendacja dopasowana do klienta")


@rule("76b")
def advisory_instruments(ctx: RuleContext) -> Outcome:
    """Art. 76 b: concerns financial instruments."""
    return _element(ctx, "advisory_instruments", "instrumenty finansowe")


@rule("76c")
def advisory_buy_sell(ctx: RuleContext) -> Outcome:
    """Art. 76 c: buy / sell / hold recommendations."""
    return _element(ctx, "advisory_buy_sell", "rekomendacje kup / sprzedaj / trzymaj")


@rule("76d")
def advisory_poland(ctx: RuleContext) -> Outcome:
    """Art. 76 d: service offered in Poland."""
    out = _element(ctx, "advisory_poland", "oferta kierowana do klientów w Polsce")
    if out.status == "pass" and ctx.lang == "pl":
        return Outcome("fail", 0.6, "Element obecny: oferta w języku polskim.")
    return out


@rule("76e")
def advisory_management(ctx: RuleContext) -> Outcome:
    """Art. 76 e: managing someone else's portfolio."""
    return _element(ctx, "advisory_management", "zarządzanie cudzym portfelem")
