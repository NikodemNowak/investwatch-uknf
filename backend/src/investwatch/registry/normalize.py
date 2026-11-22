"""Name and domain normalisation for register matching."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

import tldextract

# Longest first so "sp. z o.o. sp.k." wins over "sp. z o.o.".
_LEGAL_FORMS = [
    "spolka z ograniczona odpowiedzialnoscia",
    "spolka akcyjna",
    "spolka komandytowa",
    "sp z o o sp k",
    "sp z o o",
    "sp k",
    "s a",
    "sa",
    "ltd",
    "limited",
    "plc",
    "llc",
    "inc",
    "corp",
    "gmbh",
    "ag",
    "se",
    "aps",
    "as",
    "a s",
    "asa",
    "ab",
    "bv",
    "b v",
    "nv",
    "n v",
    "sarl",
    "s a r l",
    "sas",
    "sl",
    "s l",
    "spa",
    "s p a",
    "srl",
    "s r l",
    "oy",
    "oyj",
    "uab",
    "kft",
    "zrt",
    "ead",
    "ad",
    "doo",
    "d o o",
    "sro",
    "s r o",
    "ou",
    "co",
    "kg",
    "mbh",
    "eood",
]
_LEGAL_RE = re.compile(r"(?:\s(?:" + "|".join(re.escape(f) for f in _LEGAL_FORMS) + r"))+$")
_TRAILING_BRANCH = re.compile(r"\s(?:oddzial w polsce|oddzial|branch(?: in poland)?)$")

GENERIC_TOKENS = frozenset(
    [
        "a",
        "and",
        "the",
        "of",
        "for",
        "in",
        "on",
        "to",
        "i",
        "w",
        "z",
        "na",
        "do",
        "oraz",
        "und",
        "et",
        "de",
        "des",
        "du",
        "la",
        "le",
        "der",
        "die",
        "das",
        "von",
        "bank",
        "banku",
        "banki",
        "bankowy",
        "bankowa",
        "banking",
        "dom",
        "domu",
        "maklerski",
        "maklerskie",
        "maklerska",
        "maklerskiego",
        "dm",
        "bm",
        "biuro",
        "departament",
        "makler",
        "broker",
        "brokers",
        "brokerage",
        "brokerski",
        "oddzial",
        "branch",
        "polska",
        "polski",
        "polskie",
        "poland",
        "polish",
        "europe",
        "european",
        "europa",
        "eu",
        "international",
        "global",
        "group",
        "grupa",
        "holding",
        "holdings",
        "capital",
        "kapital",
        "invest",
        "inwest",
        "investment",
        "investments",
        "inwestycje",
        "inwestycyjny",
        "inwestycyjna",
        "inwestycyjne",
        "inwestycji",
        "inwestycyjnych",
        "market",
        "markets",
        "trade",
        "trading",
        "trader",
        "traders",
        "finance",
        "financial",
        "finanse",
        "finansowy",
        "finansowe",
        "finansowa",
        "securities",
        "security",
        "asset",
        "assets",
        "management",
        "manager",
        "managers",
        "wealth",
        "fund",
        "funds",
        "fundusz",
        "fundusze",
        "partners",
        "partner",
        "services",
        "service",
        "solutions",
        "advisors",
        "advisers",
        "advisory",
        "consulting",
        "company",
        "corporation",
        "cyprus",
        "cy",
        "fx",
        "forex",
        "cfd",
        "cfds",
        "prime",
        "online",
        "direct",
        "digital",
        "exchange",
        "exchanges",
        "limited",
        "ltd",
        "sa",
        "spolka",
        "akcyjna",
        "kasa",
        "towarzystwo",
        "tfi",
        "private",
        "equity",
        "bonds",
        "stocks",
        "first",
        "one",
        "new",
        "world",
        "united",
        "union",
        "mutual",
    ]
)
"""Words that never identify a firm on their own (stop-list against false positives)."""

GENERIC_STEMS = (
    "invest", "inwest", "trade", "trading", "trader", "financ", "finans", "capital", "kapital",
    "market", "secur", "broker", "makler", "bank", "asset", "wealth", "fund", "manag", "partner",
    "advis", "consult", "servic", "solution", "global", "group", "holding", "exchang", "inwestor",
    "portfel", "portfol", "zysk", "profit", "money", "pieniad", "gield", "stock", "forex", "crypto",
    "handlow", "niezalezn",
)  # fmt: skip
"""Prefixes of inflected generic words ("investors", "inwestorów"): never a one-word brand."""

COMMON_WORDS = frozenset(
    [
        "plus",
        "b2b",
        "b2c",
        "zloto",
        "zlota",
        "gold",
        "silver",
        "alfa",
        "alpha",
        "beta",
        "delta",
        "gamma",
        "omega",
        "nova",
        "nobel",
        "noble",
        "ever",
        "easy",
        "smart",
        "best",
        "top",
        "max",
        "pro",
        "next",
        "future",
        "fusion",
        "legacy",
        "vision",
        "atlas",
        "orion",
        "phoenix",
        "titan",
        "apex",
        "summit",
        "horizon",
        "star",
        "stars",
        "sun",
        "blue",
        "green",
        "red",
        "black",
        "white",
        "gold",
        "golden",
        "royal",
        "crown",
    ]
)
"""Dictionary words that are distinctive in a firm name but too common to match on alone."""

_TOKEN = re.compile(r"[a-z0-9]+")
_DOMAIN_IN_TEXT = re.compile(
    r"(?<![\w@.-])(?:https?://)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![\w-])"
    r"(/[^\s\"'<>),;]*)?",
    re.IGNORECASE,
)

PLATFORM_DOMAINS = frozenset(
    [
        "facebook.com",
        "fb.com",
        "instagram.com",
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "t.me",
        "telegram.org",
        "whatsapp.com",
        "google.com",
        "apple.com",
        "bit.ly",
        "tinyurl.com",
        "linktr.ee",
        "wikipedia.org",
        "knf.gov.pl",
        "gov.pl",
    ]
)
"""Shared platforms: never a firm's own domain, even when a register entry links to them."""


def fold(text: str) -> str:
    """Casefold and strip diacritics (`Łódź` -> `lodz`)."""
    text = text.replace("ł", "l").replace("Ł", "L").replace("ß", "ss")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def tokens(text: str) -> list[str]:
    """Folded alphanumeric tokens."""
    return _TOKEN.findall(fold(text))


def strip_legal_form(name: str) -> str:
    """Return the folded name without its legal form and "branch in Poland" suffix."""
    folded = " ".join(tokens(re.sub(r"\([^)]*\)", " ", name)))
    previous = None
    while previous != folded:
        previous = folded
        folded = _TRAILING_BRANCH.sub("", folded)
        stripped = _LEGAL_RE.sub("", " " + folded).strip()
        folded = stripped or folded
    return folded


def legal_form_of(name: str) -> str | None:
    """Return the legal-form suffix of a name as written (e.g. `S.A.`), if any."""
    plain = re.sub(r"\([^)]*\)", " ", name)
    core = strip_legal_form(plain)
    words = plain.split()
    for i in range(1, len(words)):
        if " ".join(tokens(" ".join(words[:i]))) == core:
            return " ".join(words[i:]).strip(" ,") or None
    return None


def is_distinctive(key_tokens: list[str]) -> bool:
    """True when a name has a token that can identify a firm on its own."""
    return any(t not in GENERIC_TOKENS and len(t) >= 3 for t in key_tokens)


_RESERVED_TLDS = frozenset({"example", "test", "invalid", "localhost"})

# Bundled public-suffix snapshot: no network call at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=())


def registrable_domain(url_or_host: str) -> str:
    """Registrable domain of a URL or host; bare internal hosts (`demo-sites`) stay as they are.

    Returns "" for things that only look like domains (`ul.pu` in "ul.Puławska").
    """
    value = url_or_host.strip().strip("/;,").lower()
    if not value:
        return ""
    try:
        host = urlsplit(value if "://" in value else f"http://{value}").hostname or ""
    except ValueError:  # malformed URL in a register note
        return ""
    if "." not in host:
        return host
    parts = _extract(host)
    if parts.suffix:
        return parts.top_domain_under_public_suffix
    labels = host.split(".")
    # RFC 2606 reserved TLDs: the fictional demo firms live on `*.example`.
    return ".".join(labels[-2:]) if labels[-1] in _RESERVED_TLDS else ""


def host_path(url: str) -> str:
    """`host/path` without scheme, `www.` and query, for prefix ownership rules."""
    try:
        parts = urlsplit(url if "://" in url else f"http://{url}")
    except ValueError:
        return ""
    host = (parts.hostname or "").lower().removeprefix("www.")
    return f"{host}{parts.path}".rstrip("/")


def domains_in_text(text: str) -> list[tuple[str, str]]:
    """Return (registrable domain, matched text) for each URL or bare domain in `text`."""
    found: list[tuple[str, str]] = []
    for match in _DOMAIN_IN_TEXT.finditer(text):
        host = match.group(1)
        domain = registrable_domain(host)
        if domain:
            found.append((domain, match.group(0)))
    return found


def handle_key(handle: str) -> str:
    """Compare form of a social handle or page name: folded alphanumerics only."""
    return "".join(tokens(handle.removeprefix("@")))
