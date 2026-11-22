"""Common Crawl URL index: the pages of one domain that Common Crawl saw (optional).

`index.commoncrawl.org` is heavily rate-limited and often answers 5xx; one try with a short
timeout, answers cached for 7 days, and any failure is an empty list plus a warning, never a
failed run. Terms: commoncrawl.org/terms-of-use (lawful use, third-party rights respected).
"""

from __future__ import annotations

import json
import logging

import httpx

from investwatch.collectors.base import PoliteFetcher
from investwatch.collectors.discovery.cache import TextCache, get_cache
from investwatch.collectors.official.http import api_client
from investwatch.config import Settings, get_settings

log = logging.getLogger(__name__)

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
CACHE_TTL_S = 7 * 24 * 3600
TIMEOUT_S = 20.0
LIMIT = 200


def commoncrawl_urls(
    domain: str,
    *,
    settings: Settings | None = None,
    fetcher: PoliteFetcher | None = None,
    transport: httpx.BaseTransport | None = None,
    cache: TextCache | None = None,
) -> list[str]:
    """HTML pages of `domain` (status 200) from the newest (or configured) crawl index."""
    settings = settings or get_settings()
    if not settings.commoncrawl_enabled:
        return []
    cache = cache or get_cache()
    fetcher = fetcher or PoliteFetcher(settings)
    key = f"iw:cc:{settings.commoncrawl_index or 'latest'}:{domain}"
    cached = cache.get(key)
    if cached is not None:
        return list(json.loads(cached))
    try:
        with api_client(fetcher, settings, transport) as client:
            client.timeout = httpx.Timeout(TIMEOUT_S)
            api = _index_api(client, settings.commoncrawl_index)
            fetcher.wait(api)
            response = client.get(
                api,
                params={
                    "url": f"{domain}/*",
                    "output": "json",
                    "fl": "url,timestamp,status,mime",
                    "filter": "status:200",
                    "limit": LIMIT,
                },
            )
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("common crawl unavailable for %s: %s", domain, type(exc).__name__)
        return []
    if response.status_code >= 400:
        log.warning("common crawl HTTP %s for %s; skipping", response.status_code, domain)
        return []
    urls: list[str] = []
    for line in response.text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if "html" in str(row.get("mime") or "html") and row.get("url"):
            urls.append(str(row["url"]))
    urls = list(dict.fromkeys(urls))
    cache.set(key, json.dumps(urls), CACHE_TTL_S)
    return urls


def _index_api(client: httpx.Client, index: str) -> str:
    if index:
        return f"https://index.commoncrawl.org/{index}-index"
    response = client.get(COLLINFO_URL)
    response.raise_for_status()
    crawls = response.json()
    if not crawls:
        raise ValueError("empty collinfo.json")
    return str(crawls[0]["cdx-api"])
