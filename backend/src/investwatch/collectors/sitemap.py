"""Sitemaps and feeds: robots.txt `Sitemap:` -> sitemap(-index) XML, gzip, RSS/Atom -> URLs.

Only what the site owner publishes for crawlers is used. Limits keep one domain cheap: at most
`MAX_FILES` sitemap files and `MAX_URLS` URLs per domain and run.
"""

from __future__ import annotations

import gzip
import io
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlsplit

from investwatch.collectors.base import PoliteFetcher, domain_of

log = logging.getLogger(__name__)

MAX_FILES = 5
MAX_URLS = 2000
MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class SitemapUrl:
    """One `<url>` (or feed item) with its last modification date, if given."""

    loc: str
    lastmod: str = ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def decode_body(content: bytes) -> bytes:
    """Gunzip `.xml.gz` sitemaps (bounded), pass anything else through."""
    if content[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as fh:
            data = fh.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("sitemap larger than the limit")
        return data
    return content


def parse_sitemap(content: bytes) -> tuple[list[SitemapUrl], list[str]]:
    """Return (page URLs, child sitemaps) of a sitemap, sitemap index, RSS or Atom feed."""
    try:
        root = ET.fromstring(decode_body(content))
    except (ET.ParseError, ValueError, OSError) as exc:
        log.info("not a sitemap: %s", exc)
        return [], []
    kind = _local(root.tag)
    urls: list[SitemapUrl] = []
    children: list[str] = []
    if kind in {"urlset", "sitemapindex"}:
        for entry in root:
            fields = {_local(c.tag): (c.text or "").strip() for c in entry}
            loc = fields.get("loc")
            if not loc:
                continue
            if _local(entry.tag) == "sitemap":
                children.append(loc)
            else:
                urls.append(SitemapUrl(loc, fields.get("lastmod", "")))
    elif kind in {"rss", "rdf"}:
        for item in root.iter():
            if _local(item.tag) == "item":
                fields = {_local(c.tag): (c.text or "").strip() for c in item}
                if fields.get("link"):
                    urls.append(SitemapUrl(fields["link"], fields.get("pubdate", "")))
    elif kind == "feed":
        for entry in root:
            if _local(entry.tag) != "entry":
                continue
            link = next(
                (c.get("href") for c in entry if _local(c.tag) == "link" and c.get("href")), None
            )
            updated = next((c.text or "" for c in entry if _local(c.tag) == "updated"), "")
            if link:
                urls.append(SitemapUrl(link, updated.strip()))
    return urls[:MAX_URLS], children


def sitemap_urls(fetcher: PoliteFetcher, origin: str) -> list[SitemapUrl]:
    """Every page URL the origin's sitemaps list (same registrable domain only)."""
    origin = origin.rstrip("/")
    queue = fetcher.sitemaps(f"{origin}/") or [f"{origin}/sitemap.xml"]
    seen: set[str] = set()
    found: dict[str, SitemapUrl] = {}
    domain = domain_of(origin)
    while queue and len(seen) < MAX_FILES and len(found) < MAX_URLS:
        url = queue.pop(0)
        if url in seen or domain_of(url) != domain:
            continue
        seen.add(url)
        result = fetcher.fetch(url)
        if result.fetch_status != "ok" or not result.content:
            log.info("sitemap %s: %s %s", url, result.fetch_status, result.error or "")
            continue
        pages, children = parse_sitemap(result.content)
        queue += [c for c in children if c not in seen]
        for page in pages:
            if domain_of(page.loc) == domain and urlsplit(page.loc).scheme in {"http", "https"}:
                found.setdefault(page.loc, page)
    return list(found.values())[:MAX_URLS]


def keyword_filter(urls: list[SitemapUrl], keywords: list[str]) -> list[SitemapUrl]:
    """URLs whose path mentions a keyword, newest `lastmod` first."""
    hits = [u for u in urls if any(k in u.loc.lower() for k in keywords)]
    return sorted(hits, key=lambda u: u.lastmod, reverse=True)
