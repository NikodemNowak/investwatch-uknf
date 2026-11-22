"""Analyst submissions: a URL plus the text the analyst saw (and an optional screenshot).

This is the only path for organic Facebook, Instagram and TikTok posts: nothing is fetched,
the analyst supplies the material. Pasted text without a URL
goes through the same function.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import urlsplit

from investwatch.collectors.base import domain_of
from investwatch.collectors.platform import envelope
from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import Platform

_HOST_PLATFORM: dict[str, Platform] = {
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "fb.watch": "facebook",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
}


def platform_of_url(url: str) -> Platform:
    """Our platform for a URL (social hosts by registrable domain, everything else `web`)."""
    return _HOST_PLATFORM.get(domain_of(url).lower(), "web") if url else "web"


def submission_item(
    text: str,
    url: str | None = None,
    *,
    screenshot: bytes | None = None,
    submitted_by: str = "analyst",
    note: str = "",
) -> CollectedItem:
    """Wrap an analyst's submission as an item so it goes through the same pipeline."""
    body = text.strip()
    link = (url or "").strip()
    digest = hashlib.sha256(f"{link}\n{body}".encode()).hexdigest()[:16]
    ident = f"submission:{digest}" if link else f"text:{digest}"
    host = urlsplit(link).hostname or "" if link else ""
    return CollectedItem(
        platform=platform_of_url(link),
        collector="analyst",
        external_id=ident,
        url=link or ident,
        author=host or "(wklejony tekst)",
        text=body,
        fetch_status="ok" if body else "no_text",
        screenshots={"desktop": screenshot} if screenshot else {},
        raw=envelope(
            "analyst",
            link or ident,
            link or "text",
            {},
            submitted_by=submitted_by,
            submitted_at=datetime.now(UTC).isoformat(),
            note=note,
            screenshot_sha256=hashlib.sha256(screenshot).hexdigest() if screenshot else None,
        ),
    )
