"""Headless Chromium for the `web` collector: one browser per thread, one context per page.

Launching Chromium costs ~0.5 s, so the browser is reused for the life of the worker process;
each page gets a fresh context (cookies, UA, proxy) that is closed afterwards.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Playwright,
    ProxySettings,
    Request,
    Route,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, ConfigDict

from investwatch.collectors.policy import platform_rejection
from investwatch.config import Settings, get_settings
from investwatch.core.schemas import RenderSnapshot, Viewport
from investwatch.render.capture import VIEWPORTS, capture

log = logging.getLogger(__name__)

UrlGuard = Callable[[str], str | None]
"""Returns why a URL must not be loaded, or None when it is fine."""


class BlockedNavigationError(RuntimeError):
    """The page (or a redirect on the way to it) points at a forbidden address."""


class RenderResult(BaseModel):
    """What one render produced."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    final_url: str
    html: str
    """Rendered DOM (after scripts ran), not the bytes the server sent."""
    snapshot: RenderSnapshot
    screenshots: dict[Viewport, bytes]


class Renderer:
    """Loads a URL in headless Chromium and captures it in all viewports."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Nothing is launched until the first `render`."""
        self._settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def _ensure_browser(self) -> Browser:
        if self._browser is not None and self._browser.is_connected():
            return self._browser
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        # Docker's 64 MB /dev/shm is too small for Chromium's shared memory.
        self._browser = self._playwright.chromium.launch(args=["--disable-dev-shm-usage"])
        return self._browser

    def render(
        self,
        url: str,
        *,
        user_agent: str | None = None,
        proxy: str | None = None,
        guard: UrlGuard | None = None,
    ) -> RenderResult:
        """Open `url`, wait for it to load and capture it; raises on navigation failure.

        Platform and search-engine hosts are refused on every request (page, frames, assets)
        whatever `guard` says: they are reached only through their official APIs.
        """
        guard = _with_platform_guard(guard)
        browser = self._ensure_browser()
        context = browser.new_context(
            viewport=VIEWPORTS["desktop"],
            user_agent=user_agent,
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            service_workers="block",
            proxy=ProxySettings(server=proxy) if proxy else None,
        )
        timeout_ms = self._settings.render_timeout_s * 1000
        context.set_default_timeout(timeout_ms)
        try:
            reason = guard(url)
            if reason:
                raise BlockedNavigationError(f"{url}: {reason}")
            _install_guard(context, guard)
            page = context.new_page()
            response = page.goto(url, wait_until="load", timeout=timeout_ms)
            _check_redirects(page.url, response.request if response else None, guard)
            snapshot, shots = capture(page)
            return RenderResult(
                final_url=page.url, html=page.content(), snapshot=snapshot, screenshots=shots
            )
        finally:
            context.close()

    def close(self) -> None:
        """Shut the browser down (tests, worker shutdown)."""
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except PlaywrightError as exc:
            log.debug("closing browser: %s", exc)
        finally:
            self._browser = None
            self._playwright = None


def _with_platform_guard(guard: UrlGuard | None) -> UrlGuard:
    def combined(url: str) -> str | None:
        return platform_rejection(url) or (guard(url) if guard is not None else None)

    return combined


def _install_guard(context: BrowserContext, guard: UrlGuard) -> None:
    """Abort every request (page, frames, assets) to a forbidden host."""
    verdicts: dict[str, str | None] = {}

    def handler(r: Route) -> None:
        url = r.request.url
        parts = urlsplit(url)
        if parts.scheme in {"data", "blob", "about"}:
            r.continue_()
            return
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in verdicts:
            verdicts[key] = guard(url)
        if verdicts[key]:
            log.warning("render blocked request to %s: %s", key, verdicts[key])
            r.abort("blockedbyclient")
        else:
            r.continue_()

    context.route("**/*", handler)


def _check_redirects(final_url: str, request: Request | None, guard: UrlGuard) -> None:
    """Route handlers do not see redirect hops, so re-check the whole chain afterwards."""
    hops = [final_url]
    while request is not None:
        hops.append(request.url)
        request = request.redirected_from
    for hop in hops:
        reason = guard(hop)
        if reason:
            raise BlockedNavigationError(f"{hop}: {reason}")


_local = threading.local()


def get_renderer() -> Renderer:
    """Renderer for the current thread (Playwright's sync API is bound to its thread)."""
    renderer: Renderer | None = getattr(_local, "renderer", None)
    if renderer is None:
        renderer = Renderer()
        _local.renderer = renderer
    return renderer
