"""Text cleaning, light language detection and sentence splitting."""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

_HTML_TAG = re.compile(r"<(?:[a-zA-Z][\w:-]*|/[a-zA-Z][\w:-]*|!--)[^>]*>")
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
_SPACES = re.compile(r"[^\S\n]+")
_NEWLINES = re.compile(r"\s*\n\s*")
_WORD = re.compile(r"[^\W\d_]+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")
# "S.A. jest", "ul. Prosta", "np. akcje" must not end a sentence.
_ABBREV_END = re.compile(
    r"(?:\b\w\.|\b(?:ul|np|tzw|ok|sp|nr|al|tj|ds|mies|godz|zł|ust|lit|art|pkt|del|m\.in)\.)$",
    re.IGNORECASE,
)

_BLOCK_TAGS = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    ]
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head"})

# Small closed-class word lists: enough to tell Polish from English/German on short posts.
_STOPWORDS: dict[str, frozenset[str]] = {
    "pl": frozenset(
        [
            "i",
            "w",
            "z",
            "na",
            "do",
            "się",
            "nie",
            "to",
            "że",
            "jest",
            "są",
            "od",
            "za",
            "po",
            "jak",
            "o",
            "dla",
            "czy",
            "ale",
            "lub",
            "oraz",
            "już",
            "tylko",
            "przez",
            "przy",
            "może",
            "być",
            "ze",
            "co",
            "ich",
            "jego",
            "twoje",
            "twój",
            "nasz",
            "nasze",
            "który",
            "która",
            "które",
            "również",
            "wiąże",
            "części",
            "całości",
            "kapitału",
            "ryzykiem",
        ]
    ),
    "en": frozenset(
        [
            "the",
            "and",
            "of",
            "to",
            "in",
            "is",
            "are",
            "a",
            "an",
            "with",
            "for",
            "on",
            "that",
            "this",
            "be",
            "by",
            "or",
            "your",
            "our",
            "you",
            "from",
            "as",
            "at",
            "it",
            "not",
            "can",
            "may",
            "come",
            "when",
            "lose",
            "money",
            "high",
            "risk",
        ]
    ),
    "de": frozenset(
        [
            "der",
            "die",
            "das",
            "und",
            "ist",
            "sind",
            "nicht",
            "mit",
            "von",
            "zu",
            "ein",
            "eine",
            "für",
            "auf",
            "den",
            "dem",
            "des",
            "sie",
            "ihr",
            "kann",
            "können",
            "verlieren",
        ]
    ),
}
_PL_LETTERS = re.compile("[ąćęłńóśźż]", re.IGNORECASE)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def strip_html(raw: str) -> str:
    """Return the visible text of an HTML fragment, with block elements on separate lines."""
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    return "".join(parser.parts)


def clean_text(raw: str) -> str:
    """Normalise collected text: strip HTML, NFKC, drop zero-width chars, squeeze whitespace."""
    text = strip_html(raw) if _HTML_TAG.search(raw) else html.unescape(raw)
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _SPACES.sub(" ", text)
    text = _NEWLINES.sub("\n", text)
    return text.strip()


def detect_lang(text: str) -> str | None:
    """Guess "pl", "en" or "de" from stopwords and diacritics; None when there is no signal."""
    words = [w.casefold() for w in _WORD.findall(text)]
    if not words:
        return None
    scores = {lang: sum(w in sw for w in words) for lang, sw in _STOPWORDS.items()}
    scores["pl"] += 2 * len(_PL_LETTERS.findall(text))
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else None


def sentences(text: str) -> list[tuple[int, int]]:
    """Split text into sentence spans (start, end) without losing offsets."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if "\n" not in m.group() and _ABBREV_END.search(text[max(0, m.start() - 8) : m.start()]):
            continue
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans
