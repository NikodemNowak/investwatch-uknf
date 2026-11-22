"""The `web` collector: polite HTTP fetch, then a Playwright render of the same page.

HTTP first (InvestWatchBot UA, robots.txt, TDM reservations, platform deny-list, rate limit,
cooldown after a refusal, SSRF guard on every redirect hop) gives the raw
HTML exactly as served; the render then gives the text after scripts ran, the RenderSnapshot for
the visual rules (4-8, 13) and full-page screenshots. If rendering is disabled or fails, the item
still carries the HTTP text so the text rules run.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

from investwatch.collectors.base import PoliteFetcher, UrlGuard, domain_of, url_rejection
from investwatch.collectors.html_text import html_lang, html_to_text
from investwatch.collectors.platform import envelope
from investwatch.collectors.policy import platform_rejection
from investwatch.collectors.schemas import CollectedItem, FetchResult
from investwatch.config import Settings, get_settings
from investwatch.core.schemas import FetchStatus, RenderSnapshot, Viewport
from investwatch.pipeline.dedup import canonical_url
from investwatch.render.browser import Renderer, get_renderer

log = logging.getLogger(__name__)


def ssrf_guard(settings: Settings) -> UrlGuard:
    """URL guard rejecting private, loopback and link-local targets (cached per origin)."""
    allowed = settings.allowed_internal_hosts
    verdicts: dict[str, str | None] = {}

    def guard(url: str) -> str | None:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in verdicts:
            verdicts[key] = url_rejection(url, allowed)
        return verdicts[key]

    return guard


def fetch_trace(result: FetchResult) -> dict[str, Any]:
    """How the page was fetched (User-Agent, proxy, robots.txt, timing), kept in `raw.fetch`."""
    return {
        "user_agent": result.user_agent,
        "proxy": result.proxy,
        "robots": result.robots,
        "crawl_delay_s": result.crawl_delay_s,
        "http_status": result.status_code,
        "elapsed_ms": result.elapsed_ms,
        "final_url": result.final_url,
        "render": None,
    }


class WebCollector:
    """One web page: raw HTML, full visible text, RenderSnapshot and screenshots."""

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        renderer: Renderer | None = None,
        *,
        name: str = "web",
        render: bool | None = None,
        guard: UrlGuard | None = None,
        settings: Settings | None = None,
    ) -> None:
        """`render=None` follows `RENDER_ENABLED`; tests inject the fetcher and renderer."""
        self._settings = settings or get_settings()
        self._guard = guard or ssrf_guard(self._settings)
        self._fetcher = fetcher or PoliteFetcher(self._settings, url_guard=self._guard)
        self._renderer = renderer
        self._render = self._settings.render_enabled if render is None else render
        self.name = name

    def collect(self, target: str) -> list[CollectedItem]:
        """Fetch and render `target`; always returns one item (`fetch_status` says how it went)."""
        return [self.page(target)]

    def page(self, target: str, **provenance: Any) -> CollectedItem:
        """One page as an item; `provenance` (e.g. `discovered_by`) is kept in `raw`."""
        prov = {"target": target, **provenance}
        reason = platform_rejection(target) or self._guard(target)
        if reason:
            return self._item(target, "blocked", text="", html=None, error=reason, prov=prov)
        result = self._fetcher.fetch(target)
        url = result.final_url or target
        fetch = fetch_trace(result)
        prov["fetch"] = fetch
        if result.fetch_status != "ok":
            return self._item(
                url, result.fetch_status, text="", html=None, error=result.error, prov=prov
            )
        html = result.html
        text = html_to_text(html)
        lang = html_lang(html)
        render: RenderSnapshot | None = None
        shots: dict[Viewport, bytes] = {}
        is_html = "html" in (result.content_type or "text/html")
        if self._render and is_html:
            started = time.perf_counter()
            try:
                rendered = (self._renderer or get_renderer()).render(
                    url,
                    user_agent=result.user_agent or self._fetcher.user_agent(),
                    proxy=self._fetcher.proxy(),
                    guard=self._guard,
                )
            except Exception as exc:  # a broken page must not lose the text we already have
                log.warning("render failed for %s: %s", url, exc)
                fetch["render"] = f"error: {exc}"[:300]
            else:
                fetch["render"] = "ok"
                fetch["render_ms"] = round((time.perf_counter() - started) * 1000, 1)
                url = rendered.final_url
                text = html_to_text(rendered.html) or text
                lang = lang or html_lang(rendered.html)
                render, shots = rendered.snapshot, rendered.screenshots
        status: FetchStatus = "ok" if text else "no_text"
        return self._item(
            url, status, text=text, html=html, lang=lang, render=render, shots=shots, prov=prov
        )

    def _item(
        self,
        url: str,
        status: FetchStatus,
        *,
        text: str,
        html: str | None,
        lang: str | None = None,
        render: RenderSnapshot | None = None,
        shots: dict[Viewport, bytes] | None = None,
        error: str | None = None,
        prov: dict[str, Any] | None = None,
    ) -> CollectedItem:
        domain = domain_of(url)
        extra = dict(prov or {})
        target = str(extra.pop("target", url))
        return CollectedItem(
            platform="web",
            collector=self.name,
            external_id=canonical_url(url),
            url=url,
            author=domain or url,
            author_url=f"{url.split('://', 1)[0]}://{domain}" if domain else None,
            text=text,
            lang=lang,
            fetch_status=status,
            html=html or None,
            render=render,
            screenshots=shots or {},
            error=error,
            raw=envelope(self.name, url, target, {}, **extra),
        )
