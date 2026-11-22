"""Helpers shared by the collectors (official APIs, imports, crawler).

Every platform collector fails soft: a blocked or broken target becomes one item with
`fetch_status` set and `error` filled, never an exception that kills the scrape run.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from investwatch.collectors.base import domain_of
from investwatch.collectors.policy import COLLECTOR_VERSION, access_mode_of, legal_basis_of
from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import FetchStatus, Platform

_LIMIT = re.compile(r"^\s*(\d{1,3})\s*:\s*(.+)$", re.S)
_LINK = re.compile(r"https?://[^\s<>\"'()\[\]{}|]+", re.I)
_TRAILING = ".,;:!?…»”’"

# Hosts that are platforms or link shorteners, not candidate firm domains.
NON_FIRM_DOMAINS = frozenset(
    {
        "youtube.com", "youtu.be", "google.com", "facebook.com", "fb.com", "instagram.com",
        "tiktok.com", "twitter.com", "x.com", "linkedin.com", "t.me", "telegram.me",
        "discord.gg", "discord.com", "spotify.com", "apple.com", "patreon.com", "bit.ly",
        "linktr.ee", "goo.gl", "tinyurl.com", "wikipedia.org", "threads.net",
    }
)  # fmt: skip

_BLOCK_HINTS = (
    "sign in",
    "log in",
    "login",
    "zaloguj",
    "confirm you",
    "captcha",
    "not a bot",
    "private video",
    "members-only",
    "age-restricted",
    "verify your age",
    "rate-limit",
    "rate limit",
    "too many requests",
    "http error 403",
    "http error 429",
    "geo-restrict",
    "geo restrict",
    "not available in your country",
)


def split_limit(target: str, default: int) -> tuple[int, str]:
    """Split an optional `N:` prefix off `target` ("3:kod promocyjny XTB" -> 3, "kod ...")."""
    match = _LIMIT.match(target)
    if match and not target.lstrip().lower().startswith(("http:", "https:")):
        return max(1, int(match.group(1))), match.group(2).strip()
    return default, target.strip()


def extract_links(text: str) -> list[str]:
    """Return the http(s) links in `text`, in order, without duplicates."""
    links = (m.group(0).rstrip(_TRAILING) for m in _LINK.finditer(text or ""))
    return list(dict.fromkeys(links))


def candidate_domains(links: list[str]) -> list[str]:
    """Registrable domains of `links` that could belong to a firm (platforms dropped)."""
    domains = (domain_of(link).lower() for link in links)
    return list(dict.fromkeys(d for d in domains if d and d not in NON_FIRM_DOMAINS))


def classify_error(message: str) -> FetchStatus:
    """Map an extractor error to `blocked` (login wall, captcha, geo, rate limit) or `error`."""
    lowered = message.lower()
    return "blocked" if any(hint in lowered for hint in _BLOCK_HINTS) else "error"


def envelope(
    collector: str, source_url: str, target: str, data: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    """Wrap source JSON with provenance: who fetched it, how, on what basis, from where, when.

    `access_mode` and `legal_basis` default to the collector's; an import or a submission
    overrides them through `extra`.
    """
    return {
        "collector": collector,
        "collector_version": COLLECTOR_VERSION,
        "access_mode": access_mode_of(collector),
        "legal_basis": legal_basis_of(collector),
        "source_url": source_url,
        "target": target,
        "fetched_at": datetime.now(UTC).isoformat(),
        **extra,
        "data": data,
    }


def failed_item(
    collector: str,
    platform: Platform,
    target: str,
    status: FetchStatus,
    error: str,
    url: str | None = None,
) -> CollectedItem:
    """One placeholder item that records why `target` could not be collected."""
    return CollectedItem(
        platform=platform,
        collector=collector,
        external_id=f"{collector}:{target}"[:500],
        url=url or target,
        author=collector,
        text="",
        fetch_status=status,
        error=error[:1000],
        raw=envelope(collector, url or target, target, {}, error=error[:1000]),
    )


def from_timestamp(value: Any) -> datetime | None:
    """Unix seconds (int, float or numeric string) to an aware datetime."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, UTC) if seconds > 0 else None


def join_text(*parts: str | None) -> str:
    """Join non-empty parts with blank lines (the order is the reading order for rules)."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
