"""Collector output: what a collector knows before the pipeline assigns ids and hashes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from investwatch.core.schemas import FetchStatus, Platform, RenderSnapshot, Viewport

RobotsDecision = Literal["allowed", "disallowed", "missing"]
"""`missing`: no robots.txt (4xx) or unreachable, so allowed by RFC 9309."""


class CollectedItem(BaseModel):
    """One publication as returned by a collector."""

    platform: Platform
    collector: str
    external_id: str
    url: str
    author: str
    author_url: str | None = None
    text: str
    lang: str | None = None
    published_at: datetime | None = None
    fetch_status: FetchStatus = "ok"
    html: str | None = None
    render: RenderSnapshot | None = None
    screenshots: dict[Viewport, bytes] = {}
    post_id: UUID | None = None
    """Fixed id (fixtures); otherwise the pipeline generates one."""
    raw: dict[str, Any] | None = None
    """Source JSON (platform metadata, fetch time, source URL), stored as `raw/<post>.json`."""
    error: str | None = None
    """Why the fetch failed (blocked/error items); reported on the scrape run."""


class FetchResult(BaseModel):
    """Outcome of one polite HTTP fetch."""

    url: str
    final_url: str
    status_code: int | None
    html: str
    content_type: str | None
    fetch_status: FetchStatus
    error: str | None = None
    content: bytes | None = None
    """Body bytes as served (sitemaps may be gzip files); None unless the fetch succeeded."""
    user_agent: str | None = None
    """User-Agent the request went out with (always names InvestWatchBot)."""
    proxy: str | None = None
    """Egress proxy as `scheme://host:port` (credentials stripped); None = direct."""
    robots: RobotsDecision | None = None
    """What robots.txt said about this URL; None when the fetch stopped before asking."""
    crawl_delay_s: float | None = None
    elapsed_ms: float | None = None
    """Wall time of the GET itself (rate-limit wait excluded)."""
