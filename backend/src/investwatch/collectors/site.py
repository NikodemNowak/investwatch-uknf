"""The `site` collector: pages of firm websites discovered without a search engine.

Targets:
- a domain or URL (`xtb.com`, `https://www.xtb.com/pl`);
- `registry:<firm kind>` or `registry:all`: domains of KNF-register firms (rotated daily);
- `gdelt:<phrase>`: news articles from GDELT (only with `GDELT_ENABLED=true`).

Per domain: robots.txt -> `Sitemap:` (or `/sitemap.xml`) -> URLs filtered by
`SITE_URL_KEYWORDS`, newest first (a sitemap of at most 50 URLs is taken whole when none
matches); no sitemap -> the Common Crawl index (optional) -> the
home page and its internal links (depth 1). At most `[N:]`/`PLATFORM_MAX_ITEMS` pages per run go
to the `web` crawler, which applies robots.txt, TDM reservations and the rate limit to each.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from investwatch.collectors.base import PoliteFetcher, domain_of
from investwatch.collectors.discovery.commoncrawl import commoncrawl_urls
from investwatch.collectors.discovery.gdelt import CITATION, gdelt_articles
from investwatch.collectors.discovery.registry_domains import registry_domains
from investwatch.collectors.platform import failed_item, split_limit
from investwatch.collectors.policy import platform_rejection
from investwatch.collectors.schemas import CollectedItem
from investwatch.collectors.sitemap import SitemapUrl, keyword_filter, sitemap_urls
from investwatch.collectors.web import WebCollector
from investwatch.config import Settings, get_settings

log = logging.getLogger(__name__)

SMALL_SITE = 50
"""A sitemap this short is checked in full when no URL matches the keywords."""


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def internal_links(html: str, base: str) -> list[str]:
    """Same-domain http(s) links of a page, without fragments, in order."""
    parser = _Links()
    parser.feed(html)
    domain = domain_of(base)
    links = []
    for href in parser.hrefs:
        url = urljoin(base, href).split("#", 1)[0]
        if urlsplit(url).scheme in {"http", "https"} and domain_of(url) == domain:
            links.append(url)
    return list(dict.fromkeys(links))


class SiteCollector:
    """Discover a domain's relevant pages from what it publishes for crawlers, then fetch them."""

    name = "site"

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        web: WebCollector | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        """Tests inject the fetcher and the web collector."""
        self._settings = settings or get_settings()
        self._fetcher = fetcher or PoliteFetcher(self._settings)
        self._web = web or WebCollector(fetcher=self._fetcher, name="site", settings=self._settings)

    def collect(self, target: str) -> list[CollectedItem]:
        """Pages for `target`; never raises."""
        limit, rest = split_limit(target, self._settings.platform_max_items)
        rest = rest.strip()
        try:
            if rest.lower().startswith("gdelt:"):
                return self._gdelt(rest[6:].strip(), limit, target)
            if rest.lower().startswith("registry:"):
                domains = registry_domains(rest[9:].strip(), self._settings)
                if domains:  # rotate so every firm is visited over the days
                    shift = datetime.now(UTC).timetuple().tm_yday % len(domains)
                    domains = domains[shift:] + domains[:shift]
            else:
                domains = [rest]
            items: list[CollectedItem] = []
            for domain in domains:
                if len(items) >= limit:
                    break
                items += self._domain(domain, limit - len(items), target)
            return items
        except Exception as exc:  # a broken source must not crash the scrape run
            log.warning("site discovery failed for %r: %s", target, exc)
            return [failed_item(self.name, "web", target, "error", str(exc))]

    def _domain(self, domain: str, limit: int, target: str) -> list[CollectedItem]:
        origin = domain if "://" in domain else f"https://{domain}"
        parts = urlsplit(origin)
        origin = f"{parts.scheme}://{parts.netloc}"
        reason = platform_rejection(origin)
        if reason:
            return [failed_item(self.name, "web", target, "blocked", reason, url=origin)]
        keywords = self._settings.url_keywords
        listed = sitemap_urls(self._fetcher, origin)
        urls, how = keyword_filter(listed, keywords), "sitemap"
        if not urls and len(listed) <= SMALL_SITE:  # a small site is cheap to check in full
            urls = sorted(listed, key=lambda u: u.lastmod, reverse=True)
        if not urls:
            cc = [
                SitemapUrl(u) for u in commoncrawl_urls(domain_of(origin), settings=self._settings)
            ]
            urls, how = keyword_filter(cc, keywords), "commoncrawl"
        if not urls:
            urls, how = self._home_links(origin, keywords), "homepage"
        log.info("site %s: %d candidate pages via %s", origin, len(urls), how)
        return [
            self._web.page(u.loc, discovered_by={"method": how, "seed": origin, "target": target})
            for u in urls[:limit]
        ]

    def _home_links(self, origin: str, keywords: list[str]) -> list[SitemapUrl]:
        home = self._fetcher.fetch(f"{origin}/")
        if home.fetch_status != "ok":
            return [SitemapUrl(f"{origin}/")]
        links = [SitemapUrl(u) for u in internal_links(home.html, home.final_url)]
        return keyword_filter(links, keywords) or [SitemapUrl(home.final_url)]

    def _gdelt(self, query: str, limit: int, target: str) -> list[CollectedItem]:
        if not self._settings.gdelt_enabled:
            return [
                failed_item(self.name, "web", target, "blocked", "GDELT disabled (GDELT_ENABLED)")
            ]
        articles = gdelt_articles(query, limit * 2, settings=self._settings)
        items = []
        for article in articles:
            url = str(article.get("url") or "")
            if not url or platform_rejection(url):
                continue
            items.append(
                self._web.page(
                    url, discovered_by={"method": "gdelt", "query": query, "citation": CITATION}
                )
            )
            if len(items) >= limit:
                break
        return items
