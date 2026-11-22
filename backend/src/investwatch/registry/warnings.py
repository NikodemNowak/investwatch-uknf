"""KNF public warning list: is the *publisher* of a post a listed entity?

The snapshot (`data/registry/knf_warnings.json`, `golden/sources/knf_warnings.py`) lists the
entities KNF notified to prosecutors for unauthorised financial activity. A post matches when
its URL, author URL or domain-like author is on a listed domain, or when its author name is a
listed name (exact after the register's normalisation, or RapidFuzz >= `FUZZY_MIN_SCORE`).
Mentions in the text do not count: naming a warned entity is what warnings and journalists do.

The match is a flag for the analyst and the `ai` service (M3 explanation), never a score boost.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rapidfuzz import fuzz, process

from investwatch.config import get_settings
from investwatch.core.schemas import Post
from investwatch.golden.sources.knf_warnings import URL, load_snapshot
from investwatch.registry.normalize import (
    PLATFORM_DOMAINS,
    handle_key,
    is_distinctive,
    registrable_domain,
    strip_legal_form,
)
from investwatch.registry.schemas import KnfWarning

log = logging.getLogger(__name__)

SNAPSHOT_FILE = "knf_warnings.json"
FUZZY_MIN_SCORE = 92.0
MIN_NAME_CHARS = 5
"""Shorter normalised names ("ABC") are too ambiguous to match an author on."""

_NUMBERED = re.compile(r"(?:^|\s)\d{1,2}[.)]\s+")
_NAME_END = re.compile(
    r"\s+z\s+siedzib|\s+prowadząc|\s+działając|\s+administrator|\s+operator|\s+za\s+pośrednictwem"
    r"|\s+posługując|\s+wykonując|\s+działalność\s+prowadzon|,|\s[-–]\s|\s\(|:",
    re.IGNORECASE,
)
_DOMAIN_LIKE = re.compile(r"\w\.[a-z]{2,}(?:/|\b)(?!\s*o\.)")
_PARENS = re.compile(r"\(([^)]*)\)")
_ALIAS_SPLIT = re.compile(r",\s*|\s+oraz\s+|\s+i\s+")


@dataclass(frozen=True)
class _Entry:
    name: str
    section: str


@dataclass(frozen=True)
class WarningIndex:
    """Lookup structures over the snapshot; build once per process."""

    as_of: str
    by_domain: dict[str, _Entry]
    by_key: dict[str, _Entry]
    """Normalised name (`strip_legal_form`) -> entry."""
    by_compact: dict[str, _Entry]
    """Name without spaces, to compare with social handles (`@primefx24`)."""


def entity_names(listed: str) -> list[str]:
    """Names in one warning-list cell: numbered sub-entities and aliases in parentheses."""
    out: list[str] = []
    for segment in _NUMBERED.split(listed):
        segment = segment.strip(' „"”.;')
        if not segment:
            continue
        head = _NAME_END.split(segment, maxsplit=1)[0].strip(' „"”.;')
        if head and "www" not in head.lower() and not _DOMAIN_LIKE.search(head):
            out.append(head)
        for inner in _PARENS.findall(segment):
            if "www" in inner or "." in inner.replace(". ", " "):
                continue
            out += [a.strip(' „"”') for a in _ALIAS_SPLIT.split(inner) if a.strip()]
    return list(dict.fromkeys(out))


def _usable(key: str) -> bool:
    return len(key.replace(" ", "")) >= MIN_NAME_CHARS and is_distinctive(key.split())


def build_index(path: Path) -> WarningIndex:
    """Index the snapshot's domains and names."""
    snapshot = load_snapshot(path)
    by_domain: dict[str, _Entry] = {}
    by_key: dict[str, _Entry] = {}
    by_compact: dict[str, _Entry] = {}
    for entity in snapshot.entities:
        names = entity_names(entity.name)
        # A listed domain matches even when no name can be parsed from the cell.
        first = _Entry(names[0] if names else entity.name.strip(' „"”.;'), entity.section)
        for domain in entity.domains:
            registrable = registrable_domain(domain)
            if registrable and registrable not in PLATFORM_DOMAINS:
                by_domain.setdefault(registrable, first)
        for name in names:
            key = strip_legal_form(name)
            if _usable(key):
                entry = _Entry(name, entity.section)
                by_key.setdefault(key, entry)
                by_compact.setdefault(key.replace(" ", ""), entry)
    return WarningIndex(snapshot.retrieved_at, by_domain, by_key, by_compact)


@cache
def get_index(path: Path | None = None) -> WarningIndex | None:
    """The index of the configured snapshot; None when the file is missing."""
    path = path or get_settings().registry_dir / SNAPSHOT_FILE
    if not path.exists():
        log.warning("KNF warning list %s not found; warning-list flag disabled", path)
        return None
    return build_index(path)


def _warning(index: WarningIndex, entry: _Entry, method: str, matched: str) -> KnfWarning:
    return KnfWarning.model_validate(
        {
            "name": entry.name,
            "method": method,
            "matched_text": matched,
            "section": entry.section,
            "as_of": index.as_of,
            "source_url": URL,
        }
    )


def match_warning(
    post: Post, index: WarningIndex | None = None, *, by_name: bool = True
) -> KnfWarning | None:
    """The warning-list entity that published `post`, if any.

    Args:
        post: the post to check (URL, author URL, author).
        index: the snapshot index (default: the configured file).
        by_name: also match the author name; the pipeline turns this off when the publisher is
            a registered firm, whose name may resemble a listed one.
    """
    index = index or get_index()
    if index is None:
        return None
    author = post.author.strip()
    candidates = [post.url, post.canonical_url, post.author_url or ""]
    if "." in author and " " not in author and not author.startswith("@"):
        candidates.append(author)
    for value in candidates:
        domain = registrable_domain(value) if value and not value.startswith("import:") else ""
        if domain and domain not in PLATFORM_DOMAINS and domain in index.by_domain:
            return _warning(index, index.by_domain[domain], "domain", domain)
    if not by_name or not author:
        return None
    key = strip_legal_form(author.removeprefix("@"))
    if key in index.by_key:
        return _warning(index, index.by_key[key], "name", author)
    compact = handle_key(author)
    if compact in index.by_compact:
        return _warning(index, index.by_compact[compact], "name", author)
    if not _usable(key):
        return None
    best = process.extractOne(key, index.by_key.keys(), scorer=fuzz.ratio)
    if best is not None and best[1] >= FUZZY_MIN_SCORE:
        return _warning(index, index.by_key[best[0]], "fuzzy", f"{author} ≈ {best[0]}")
    return None
