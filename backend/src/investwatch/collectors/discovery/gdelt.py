"""GDELT DOC 2.0 API: news articles in Polish matching a phrase (optional, off by default).

GDELT data is free for unlimited and unrestricted use with a citation and link
(gdeltproject.org). The API asks for at most one query every 5 seconds; we wait 6.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx

from investwatch.collectors.base import PoliteFetcher
from investwatch.collectors.discovery.cache import TextCache, get_cache
from investwatch.collectors.official.http import api_client
from investwatch.config import Settings, get_settings

log = logging.getLogger(__name__)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
CITATION = "GDELT Project (https://www.gdeltproject.org/)"
INTERVAL_S = 6.0
CACHE_TTL_S = 12 * 3600
_lock = threading.Lock()
_last = [0.0]


def gdelt_articles(
    query: str,
    limit: int = 20,
    *,
    settings: Settings | None = None,
    fetcher: PoliteFetcher | None = None,
    transport: httpx.BaseTransport | None = None,
    cache: TextCache | None = None,
) -> list[dict[str, Any]]:
    """Articles (`url`, `title`, `domain`, `seendate`); empty when disabled or on any failure."""
    settings = settings or get_settings()
    if not settings.gdelt_enabled:
        return []
    cache = cache or get_cache()
    key = f"iw:gdelt:{limit}:{query}"
    cached = cache.get(key)
    if cached is not None:
        return list(json.loads(cached))
    fetcher = fetcher or PoliteFetcher(settings)
    with _lock:
        wait = _last[0] + INTERVAL_S - time.monotonic()
        if wait > 0 and transport is None:
            time.sleep(wait)
        _last[0] = time.monotonic()
    params: dict[str, str | int] = {
        "query": f'"{query}" sourcelang:polish',
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(limit, 250),
        "sort": "datedesc",
    }
    try:
        with api_client(fetcher, settings, transport) as client:
            response = client.get(DOC_API, params=params)
        if response.status_code >= 400:
            log.warning("gdelt HTTP %s for %r; skipping", response.status_code, query)
            return []
        articles = [a for a in response.json().get("articles") or [] if isinstance(a, dict)]
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("gdelt unavailable for %r: %s", query, type(exc).__name__)
        return []
    result = [
        {k: a.get(k) for k in ("url", "title", "domain", "seendate", "language")}
        for a in articles[:limit]
    ]
    cache.set(key, json.dumps(result), CACHE_TTL_S)
    return result
