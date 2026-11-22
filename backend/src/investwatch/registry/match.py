"""Entity resolution against the KNF register.

`match_firms` decides who a post is *by* (`on="author"`) and which firms it is *about*
(`on="content"`). Author evidence, strongest first:

1. the post URL is on a firm's registered domain or a configured URL prefix (1.0);
2. the author handle is the firm's handle (0.95) or its brand plus an "official" suffix (0.85);
3. a web page on an unknown domain presents itself as the firm: its full name with the legal
   form next to a footer/legal cue ("z siedzibą", "nadzorowany przez", "jest nazwą handlową",
   "©"...) -> 0.75, flagged "domena spoza rejestru".

Anything else that names a firm is a mention. The AI router turns that into the module:
author -> M2, third-party mention -> M1, no registered publisher -> M3 gate
(`register_status`). Every match carries its method and the matched text as evidence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from rapidfuzz import fuzz

from investwatch.core.schemas import FirmMatch, Post, RegisteredFirm
from investwatch.pipeline.schemas import RegisterStatus
from investwatch.registry.normalize import (
    COMMON_WORDS,
    GENERIC_STEMS,
    GENERIC_TOKENS,
    PLATFORM_DOMAINS,
    domains_in_text,
    handle_key,
    host_path,
    is_distinctive,
    registrable_domain,
    strip_legal_form,
    tokens,
)

Method = Literal["domain", "handle", "alias", "fuzzy"]

CONF_DOMAIN_AUTHOR = 1.0
CONF_HANDLE_AUTHOR = 0.95
CONF_BRAND_HANDLE_AUTHOR = 0.85
CONF_SELF_PRESENTED = 0.75
CONF_AUTHOR_NAME = 0.85
CONF_FULL_NAME = 0.95
CONF_DOMAIN_CONTENT = 0.9
CONF_NAME = 0.9
CONF_SHORT_NAME = 0.75
CONF_HANDLE_CONTENT = 0.7
FUZZY_MIN_SCORE = 92.0
FUZZY_MIN_LEN = 6
MAX_CONTENT_MATCHES = 5
CONTEXT_WINDOW = 15
SELF_CUE_WINDOW = 12
OFF_REGISTER_NOTE = "domena spoza rejestru"

_LEADING_GENERIC = frozenset(
    {"dom", "maklerski", "biuro", "maklerskie", "departament", "dm", "bm", "bank", "banku"}
)
_GEO = frozenset(
    [
        "germany",
        "deutschland",
        "cyprus",
        "cy",
        "europe",
        "european",
        "eu",
        "ireland",
        "malta",
        "luxembourg",
        "netherlands",
        "nederland",
        "holland",
        "france",
        "espana",
        "spain",
        "italy",
        "italia",
        "austria",
        "czech",
        "slovakia",
        "estonia",
        "latvia",
        "lithuania",
        "bulgaria",
        "romania",
        "hungary",
        "greece",
        "portugal",
        "denmark",
        "sweden",
        "norway",
        "finland",
        "iceland",
        "liechtenstein",
        "gibraltar",
        "polska",
        "poland",
        "pl",
        "international",
        "global",
        # Seats that appear in register names ("W1M EUROPE" <- "London and Capital ...").
        "london",
        "dublin",
        "limassol",
        "nicosia",
        "frankfurt",
        "vienna",
        "wien",
        "paris",
        "madrid",
        "barcelona",
        "athens",
        "bratislava",
        "prague",
        "praha",
        "warsaw",
        "warszawa",
        "amsterdam",
    ]
)
"""Countries and seats: the register sometimes lists "(Ireland)" as a trade name, and a seat
alone ("London Ltd") never identifies a firm."""
_OFFICIAL_SUFFIXES = (
    "polska", "poland", "official", "oficjalny", "oficjalnie", "global", "group", "broker",
    "brokers", "markets", "invest", "pl", "eu", "com", "tv", "app", "dm", "bm",
)  # fmt: skip
_CONTEXT_PREFIXES = (
    "broker", "makler", "konto", "rachun", "inwest", "invest", "platform", "cfd", "forex", "akcj",
    "etf", "gield", "gpw", "trading", "trade", "handl", "zlecen", "portfel", "lokat", "fundusz",
    "kontrakt", "kryptowalut", "zysk", "kapital", "obligacj", "dom", "bank",
)  # fmt: skip
_SELF_CUES = (
    "siedzib", "krs", "nip", "regon", "copyright", "wlasciciel", "administrator", "operator",
    "nadzorowan", "nadzor", "zezwoleni", "licencj", "regulated", "authorised", "authorized",
    "marketingow", "zastrzezon", "handlowa", "handlowy", "wydawc", "spolka",
)  # fmt: skip
"""Footer / legal-note words around a firm's own name ("z siedzibą w", "nadzorowany przez")."""
_THIRD_PARTY_CUES = (
    "ostrzeg", "uwaga", "oszust", "scam", "nielegaln", "polecam", "recenzj", "opini", "porown",
    "ranking", "reklamuj", "artykul", "redakcj", "afiliac", "partnersk", "moj", "mojego",
)  # fmt: skip
"""Words that show a third party writes about the firm (warning, review, affiliate)."""
_ABBREVIATIONS = (("dm", ("dom", "maklerski")), ("bm", ("biuro", "maklerskie")))
"""Short forms of Polish legal descriptors used in author names ("X-Trade Brokers DM S.A.")."""
_PARENS = re.compile(r"\(([^)]*)\)")
_AD_PARTIES = re.compile(
    r"^\s*(?:Reklamodawca|Płatnik|Advertiser|Paid for by)\s*:\s*(.+?)\s*$", re.M | re.I
)
"""Advertiser / payer of record that our ad-library collectors write into the post text."""
AD_PLATFORMS = frozenset({"bing"})
"""Platforms whose post author is the advertiser of record (Microsoft Ad Library)."""
CONF_AD_PARTY = 0.85
AD_PARTY_NOTE = "reklamodawca w bibliotece reklam"
_LEGAL_TAIL = 5
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class _Key:
    firm: int
    tokens: tuple[str, ...]
    label: str
    confidence: float
    needs_upper: bool
    """Short acronym (`XTB`, `BDM`): must be written in capitals in the text."""
    needs_context: bool
    """Single-word short form: needs a finance word nearby."""
    full_name: bool
    """The registered name itself (not a trade/former name or a short form)."""


@dataclass
class _Token:
    folded: str
    original: str
    start: int
    end: int


def _variants(name: str) -> list[tuple[tuple[str, ...], bool]]:
    """Token keys for one firm name: (tokens, is_derived_short_form)."""
    core = strip_legal_form(name).split()
    # Three+ words with one specific word ("X-Trade Brokers") are specific enough as a phrase.
    if not core or not (
        is_distinctive(core) or (len(core) >= 3 and any(w not in GENERIC_TOKENS for w in core))
    ):
        return []
    out: list[tuple[tuple[str, ...], bool]] = [(tuple(core), False)]
    trimmed = list(core)
    while len(trimmed) > 1 and trimmed[0] in _LEADING_GENERIC and is_distinctive(trimmed[1:]):
        trimmed = trimmed[1:]
        out.append((tuple(trimmed), True))
    while len(trimmed) > 1 and trimmed[-1] in (GENERIC_TOKENS | _GEO | _LEADING_GENERIC):
        if not is_distinctive(trimmed[:-1]):
            break
        trimmed = trimmed[:-1]
        out.append((tuple(trimmed), True))
    return list(dict.fromkeys(out))


def _key_allowed(key: tuple[str, ...]) -> bool:
    if len(key) > 1:
        return True
    word = key[0]
    return not (
        word in GENERIC_TOKENS
        or word in _GEO
        or word in COMMON_WORDS
        or word.startswith(GENERIC_STEMS)
        or word.isdigit()
        or len(word) < 2
    )


def _distinctive(words: Iterable[str]) -> list[str]:
    return [w for w in words if w not in GENERIC_TOKENS and w not in _GEO]


class FirmIndex:
    """Lookup structures over a list of firms; build once per batch of posts."""

    def __init__(self, firms: Iterable[RegisteredFirm]) -> None:
        """Index names, aliases, domains, URL prefixes and handles."""
        self.firms = list(firms)
        self.by_domain: dict[str, set[int]] = defaultdict(set)
        self.prefixes: list[tuple[str, int]] = []
        self.by_handle: dict[str, set[int]] = defaultdict(set)
        self.brands: dict[str, set[int]] = defaultdict(set)
        self.phrases: dict[tuple[str, ...], list[_Key]] = defaultdict(list)
        self.fuzzy_by_prefix: dict[str, list[_Key]] = defaultdict(list)
        self.max_len = 1
        for i, firm in enumerate(self.firms):
            self._add_firm(i, firm)

    def _add_firm(self, i: int, firm: RegisteredFirm) -> None:
        for domain in firm.domains:
            value = domain.strip().lower()
            if "/" in value.split("://")[-1].strip("/"):
                self.prefixes.append((host_path(value), i))
                continue
            registrable = registrable_domain(value)
            if registrable and registrable not in PLATFORM_DOMAINS:
                self.by_domain[registrable].add(i)
        for handle in firm.handles:
            handle_id = handle_key(handle)
            if handle_id:
                self.by_handle[handle_id].add(i)
        names = [(firm.name, True), *((alias, False) for alias in firm.aliases)]
        for label, registered_name in names:
            for key, derived in _variants(label):
                if not _key_allowed(key):
                    continue
                single = len(key) == 1
                if derived and single:
                    confidence = CONF_SHORT_NAME
                elif derived or not registered_name:
                    confidence = CONF_NAME
                else:
                    confidence = CONF_FULL_NAME
                entry = _Key(
                    firm=i,
                    tokens=key,
                    label=label,
                    confidence=confidence,
                    needs_upper=single and len(key[0]) <= 3,
                    needs_context=single and derived,
                    full_name=registered_name and not derived,
                )
                self.phrases[key].append(entry)
                self.max_len = max(self.max_len, len(key))
                compact = "".join(key)
                if len(compact) >= 3 and not entry.needs_context:
                    self.brands[compact].add(i)
                if len(compact) >= FUZZY_MIN_LEN:
                    self.fuzzy_by_prefix[key[0][:3]].append(entry)


# ------------------------------------------------------------------ helpers


def _text_tokens(text: str) -> list[_Token]:
    out: list[_Token] = []
    for match in _WORD.finditer(text):
        original = match.group(0)
        out += [
            _Token(folded=t, original=original, start=match.start(), end=match.end())
            for t in tokens(original)
        ]
    return out


def _has_context(toks: list[_Token], start: int, end: int) -> bool:
    """A finance word within `CONTEXT_WINDOW` tokens, outside the matched span."""
    before = toks[max(0, start - CONTEXT_WINDOW) : start]
    after = toks[end : end + CONTEXT_WINDOW]
    return any(t.folded.startswith(_CONTEXT_PREFIXES) for t in [*before, *after])


def _legal_form_length(toks: list[_Token], start: int, end: int) -> int:
    """Number of tokens after the span that form a legal form (`S.A.`, `sp. z o.o.`); 0 if none."""
    span = " ".join(t.folded for t in toks[start:end])
    found = 0
    for extra in range(1, min(_LEGAL_TAIL, len(toks) - end) + 1):
        candidate = " ".join(t.folded for t in toks[start : end + extra])
        if strip_legal_form(candidate) == span:
            found = extra
    return found


def _self_presented(text: str, toks: list[_Token], start: int, end: int) -> bool:
    """A footer/legal cue next to the name: the page presents itself as this firm."""
    window = [*toks[max(0, start - SELF_CUE_WINDOW) : start], *toks[end : end + SELF_CUE_WINDOW]]
    if any(t.folded.startswith(_THIRD_PARTY_CUES) for t in window):
        return False
    if any(t.folded.startswith(_SELF_CUES) for t in window):
        return True
    lo = toks[max(0, start - 3)].start if toks else 0
    return "©" in text[lo : toks[start].start + 1]


def _platform_handle(url: str | None) -> str:
    """Handle from a social profile URL (`youtube.com/@Foo` -> `foo`), else ""."""
    if not url or "://" not in url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if registrable_domain(url) not in PLATFORM_DOMAINS:
        return ""
    segments = [s for s in parts.path.split("/") if s and s not in ("c", "user", "channel")]
    return handle_key(segments[0]) if segments else ""


def _official_brands(handle: str, index: FirmIndex) -> list[tuple[str, set[int]]]:
    """Brands whose official account this handle looks like (`xtb`, `xtbpolska`, `pl_xtb`)."""
    out: list[tuple[str, set[int]]] = []
    if handle in index.brands:
        out.append((handle, index.brands[handle]))
    for suffix in _OFFICIAL_SUFFIXES:
        for stem in (handle.removesuffix(suffix), handle.removeprefix(suffix)):
            if stem != handle and stem in index.brands:
                out.append((stem, index.brands[stem]))
    return out


class _Best:
    """Best match per firm."""

    def __init__(self, index: FirmIndex, on: Literal["author", "content"]) -> None:
        self.index, self.on = index, on
        self.found: dict[int, FirmMatch] = {}

    def add(self, i: int, confidence: float, method: Method, text: str) -> None:
        current = self.found.get(i)
        if current is None or current.confidence < confidence:
            self.found[i] = FirmMatch(
                firm=self.index.firms[i],
                confidence=round(confidence, 3),
                method=method,
                matched_text=text,
                on=self.on,
            )


# ------------------------------------------------------------------ author side


def _author_name_keys(author: str) -> list[tuple[tuple[str, ...], str]]:
    """Name keys of an author string: the name without brackets and each bracketed part.

    "X-Trade Brokers DM S.A. (XTB)" -> `x trade brokers dom maklerski`, `x trade brokers dm`,
    `xtb`; each with the original spelling (short acronyms must be in capitals).
    """
    parts = [_PARENS.sub(" ", author), *_PARENS.findall(author)]
    out: list[tuple[tuple[str, ...], str]] = []
    for part in parts:
        core = strip_legal_form(part).split()
        if not core:
            continue
        expanded: list[str] = []
        for word in core:
            expanded += next(
                (list(long) for short, long in _ABBREVIATIONS if word == short), [word]
            )
        contracted = " ".join(core)
        for short, long in _ABBREVIATIONS:
            contracted = re.sub(rf"\b{' '.join(long)}\b", short, contracted)
        for key in (tuple(core), tuple(expanded), tuple(contracted.split())):
            out.append((key, part.strip()))
    return list(dict.fromkeys(out))


def _ad_parties(post: Post) -> list[str]:
    """Advertiser and payer of an ad-library record (DSA art. 39 disclosure), if any."""
    names = [m.group(1) for m in _AD_PARTIES.finditer(post.text)]
    if post.platform in AD_PLATFORMS:
        names.insert(0, post.author)
    return [n.strip() for n in dict.fromkeys(names) if n.strip() and n.strip() != "?"]


def _brand_token(name: str) -> str:
    """First distinctive word of a name ("FxPro Financial Services Ltd" -> `fxpro`)."""
    for word in strip_legal_form(name).split():
        if len(word) >= 3 and _key_allowed((word,)) and not word.startswith(GENERIC_STEMS):
            return word
    return ""


def _ad_party_matches(post: Post, index: FirmIndex, best: _Best) -> None:
    """The advertiser or payer of record is a registered firm: the ad is the firm's own."""
    for name in _ad_parties(post):
        for key, original in _author_name_keys(name):
            if not _key_allowed(key):
                continue
            for entry in index.phrases.get(key, ()):
                if entry.needs_upper and not original.isupper():
                    continue
                best.add(entry.firm, CONF_AD_PARTY, "alias", f"{name} ({AD_PARTY_NOTE})")


def _author_name_matches(post: Post, index: FirmIndex, best: _Best) -> None:
    """A web page whose author is a firm's registered, former or trade name.

    Only for `web`: on social platforms anybody can call a page "XTB" (impersonation ads), so
    there the official handle decides. A page outside the firm's known domains keeps the
    "domena spoza rejestru" note, like a self-presentation on an unknown domain.
    """
    host = registrable_domain(post.url) if "://" in post.url else ""
    for key, original in _author_name_keys(post.author):
        if not _key_allowed(key):
            continue
        for entry in index.phrases.get(key, ()):
            if entry.needs_context or (entry.needs_upper and not original.isupper()):
                continue
            known = {registrable_domain(d) for d in index.firms[entry.firm].domains}
            if known and host not in known:
                best.add(
                    entry.firm,
                    CONF_SELF_PRESENTED,
                    "alias",
                    f"{post.author} ({OFF_REGISTER_NOTE})",
                )
            else:
                best.add(entry.firm, CONF_AUTHOR_NAME, "alias", f"{post.author} (nazwa autora)")


def _author_matches(post: Post, index: FirmIndex) -> list[FirmMatch]:
    best = _Best(index, "author")
    urls = [u for u in dict.fromkeys([post.url, post.canonical_url]) if u and "://" in u]
    prefix_hosts: set[str] = set()
    for url in urls:
        path = host_path(url)
        for prefix, i in index.prefixes:
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                best.add(i, CONF_DOMAIN_AUTHOR, "domain", prefix)
                prefix_hosts.add(registrable_domain(url))
    candidates = [*urls, post.author_url or ""]
    author = post.author.strip()
    if "." in author and " " not in author and not author.startswith("@"):
        candidates.append(author)
    for value in candidates:
        domain = registrable_domain(value) if value else ""
        if domain and domain not in PLATFORM_DOMAINS and domain not in prefix_hosts:
            for i in index.by_domain.get(domain, ()):
                best.add(i, CONF_DOMAIN_AUTHOR, "domain", domain)
    for handle in dict.fromkeys([handle_key(author), _platform_handle(post.author_url)]):
        if not handle:
            continue
        for i in index.by_handle.get(handle, ()):
            best.add(i, CONF_HANDLE_AUTHOR, "handle", post.author)
        for brand, firms in _official_brands(handle, index):
            for i in firms:
                best.add(i, CONF_BRAND_HANDLE_AUTHOR, "handle", f"{post.author} ~ {brand}")
    if post.platform == "web" and author and not author.startswith("@"):
        _author_name_matches(post, index, best)
        for bracket in _PARENS.findall(author):
            domain = registrable_domain(bracket.strip()) if "." in bracket else ""
            for i in index.by_domain.get(domain, ()) if domain else ():
                best.add(i, CONF_DOMAIN_AUTHOR, "domain", domain)
    _ad_party_matches(post, index, best)
    return list(best.found.values())


# ------------------------------------------------------------------ content side


def _content_matches(
    post: Post, index: FirmIndex, toks: list[_Token]
) -> tuple[list[FirmMatch], list[FirmMatch]]:
    """Return (mentions, self-presentations on an unknown domain)."""
    best = _Best(index, "content")
    self_presented = _Best(index, "author")
    text = post.text
    for domain, matched in domains_in_text(text):
        for i in index.by_domain.get(domain, ()):
            best.add(i, CONF_DOMAIN_CONTENT, "domain", matched)

    folded = [t.folded for t in toks]
    exact_spans: set[tuple[int, int]] = set()
    for start in range(len(toks)):
        for length in range(1, min(index.max_len, len(toks) - start) + 1):
            for entry in index.phrases.get(tuple(folded[start : start + length]), ()):
                end = start + length
                if entry.needs_upper and not toks[start].original.isupper():
                    continue
                if entry.needs_context and not _has_context(toks, start, end):
                    continue
                exact_spans.add((start, length))
                legal = _legal_form_length(toks, start, end)
                span = text[toks[start].start : toks[end + legal - 1].end]
                if legal and text[toks[end + legal - 1].end : toks[end + legal - 1].end + 1] == ".":
                    span += "."
                best.add(entry.firm, entry.confidence, "alias", span)
                if (
                    post.platform == "web"
                    and not entry.needs_context
                    and legal
                    and _self_presented(text, toks, start, end + legal)
                ):
                    self_presented.add(
                        entry.firm,
                        CONF_SELF_PRESENTED,
                        "alias",
                        f"{span} ({OFF_REGISTER_NOTE})",
                    )

    for start, tok in enumerate(toks):
        for entry in index.fuzzy_by_prefix.get(tok.folded[:3], ()):
            length = len(entry.tokens)
            if entry.firm in best.found or (start, length) in exact_spans:
                continue
            if start + length > len(toks):
                continue
            window_tokens = folded[start : start + length]
            if window_tokens == list(entry.tokens):
                continue
            # Compare only the distinctive words: "Dom Maklerski S" must not match "DM AFS".
            key_d = " ".join(_distinctive(entry.tokens))
            window_d = " ".join(_distinctive(window_tokens))
            if len(key_d) < FUZZY_MIN_LEN - 1 or not window_d:
                continue
            score = fuzz.ratio(window_d, key_d)
            if length > 1:
                score = min(
                    score, fuzz.token_set_ratio(" ".join(window_tokens), " ".join(entry.tokens))
                )
            if score < FUZZY_MIN_SCORE:
                continue
            if entry.needs_context and not _has_context(toks, start, start + length):
                continue
            confidence = 0.55 + 0.2 * (score - FUZZY_MIN_SCORE) / (100 - FUZZY_MIN_SCORE)
            span = " ".join(dict.fromkeys(t.original for t in toks[start : start + length]))
            best.add(entry.firm, confidence, "fuzzy", f"{span} ≈ {entry.label}")

    for handle in {handle_key(h) for h in re.findall(r"[@#][\w.]{3,}", text)}:
        for i in index.by_handle.get(handle, ()):
            best.add(i, CONF_HANDLE_CONTENT + 0.1, "handle", "@" + handle)
        for _brand, firms in _official_brands(handle, index):
            for i in firms:
                best.add(i, CONF_HANDLE_CONTENT, "handle", "@" + handle)

    ranked = sorted(best.found.values(), key=_rank)
    return ranked[:MAX_CONTENT_MATCHES], list(self_presented.found.values())


# ------------------------------------------------------------------ public API

_KIND_ORDER = {"dom_maklerski": 0, "bank_maklerski": 0, "oddzial_zagraniczny": 1}


def _rank(match: FirmMatch) -> tuple[float, int, str]:
    """Higher confidence first; on ties Polish firms before foreign group members."""
    return (-match.confidence, _KIND_ORDER.get(match.firm.kind, 2), match.firm.name)


LISTING_MIN_OTHER_BRANDS = 2


def _host_carries_brand(post: Post, matches: list[FirmMatch]) -> bool:
    """The page's own domain carries the firm's brand (`evodm.pl` for Evo Dom Maklerski)."""
    host = registrable_domain(post.url) if "://" in post.url else ""
    label = host.split(".")[0].replace("-", "")
    brands = {_brand_token(m.firm.name) for m in matches} - {""}
    return bool(label) and any(brand in label for brand in brands)


def _lists_several_firms(self_presented: list[FirmMatch], mentions: list[FirmMatch]) -> bool:
    """A comparison or ranking page: legal names with NIP / seat for several brands.

    A firm's own page on an unknown domain names itself; a third party that lists brokers
    ("Dane adresowe: REVOLUT LTD Oddział w Polsce ... NIP") names many. That page is about the
    firms (M1), never by one of them (M2 only for the firm's own material, ADR 0009).
    """
    own = {_brand_token(m.firm.name) or m.firm.name for m in self_presented}
    others = {
        _brand_token(m.firm.name) or m.firm.name
        for m in mentions
        if m.firm.id not in {s.firm.id for s in self_presented}
    } - own
    return len(own) > 1 or len(others) >= LISTING_MIN_OTHER_BRANDS


def match_post(post: Post, index: FirmIndex) -> list[FirmMatch]:
    """Firms the post is by (`on="author"`) or about (`on="content"`), best first."""
    authors = _author_matches(post, index)
    mentions, self_presented = _content_matches(post, index, _text_tokens(post.text))
    if not authors and (
        _host_carries_brand(post, self_presented)
        or not _lists_several_firms(self_presented, mentions)
    ):
        authors = self_presented
    # A broker's own ad: the advertiser or payer of record carries the brand of the firm the ad
    # names ("FxPro Polska" for FXPRO Financial Services Ltd). That is the firm's material (M2),
    # not a third party promoting it (M1).
    brands = {_brand_token(n) for n in _ad_parties(post)} - {""}
    if brands and not authors:
        for m in mentions:
            names = [m.firm.name, *m.firm.aliases]
            if brands & {_brand_token(n) for n in names}:
                authors.append(
                    m.model_copy(
                        update={
                            "on": "author",
                            "confidence": min(m.confidence, CONF_AD_PARTY),
                            "matched_text": f"{m.matched_text} ({AD_PARTY_NOTE})",
                        }
                    )
                )
    author_ids = {m.firm.id for m in authors}
    authors.sort(key=_rank)
    return [*authors, *(m for m in mentions if m.firm.id not in author_ids)]


def match_firms(post: Post, firms: list[RegisteredFirm]) -> list[FirmMatch]:
    """Return firms the post is by (author) or about (content), best first."""
    return match_post(post, FirmIndex(firms))


def register_status(matches: list[FirmMatch]) -> RegisterStatus:
    """Explicit M3 gate input: is the *publisher* in the KNF registers, and may it advise?

    Mentions of registered firms do not make the publisher registered.
    """
    owners = [m for m in matches if m.on == "author"]
    if not owners:
        return "not_registered"
    if any("A5" in m.firm.services for m in owners):
        return "registered"
    return "registered_without_advice"
