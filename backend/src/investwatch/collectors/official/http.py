"""HTTP client for official APIs: the crawler's honest User-Agent and egress proxy."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from investwatch.collectors.base import PoliteFetcher
from investwatch.config import Settings

SECRET_PARAMS = frozenset({"access_token", "key", "client_secret"})


def api_client(
    fetcher: PoliteFetcher, settings: Settings, transport: httpx.BaseTransport | None
) -> httpx.Client:
    """A client for one API call (no redirects: API answers are never followed elsewhere)."""
    return httpx.Client(
        transport=transport,
        proxy=None if transport else fetcher.proxy(),
        timeout=settings.collector_timeout_s,
        headers={"User-Agent": fetcher.user_agent(), "Accept": "application/json"},
    )


def strip_secrets(url: str) -> str:
    """`url` without API keys or tokens in its query (safe to log or store)."""
    parts = urlsplit(url)
    query = [
        (k, v) for k, vs in parse_qs(parts.query).items() for v in vs if k not in SECRET_PARAMS
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))
