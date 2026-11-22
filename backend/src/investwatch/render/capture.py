"""Measure a loaded page in three viewports: RenderSnapshot + full-page screenshots."""

from __future__ import annotations

import logging
from functools import cache
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, ViewportSize

from investwatch.core.schemas import RenderSnapshot, TextBlock, Viewport

log = logging.getLogger(__name__)

VIEWPORTS: dict[Viewport, ViewportSize] = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 820, "height": 1180},
    "phone": {"width": 390, "height": 844},
}
MAX_BLOCKS = 1500
MAX_TEXT_CHARS = 2000
MAX_SCREENSHOT_HEIGHT_PX = 10_000
"""Full-page screenshots are cut here; very long pages would make multi-MB images."""
LAZY_LOAD_STEPS = 25
SETTLE_TIMEOUT_MS = 1500

_LAZY_LOAD_JS = """
async (steps) => {
  const h = () => document.documentElement.scrollHeight;
  for (let i = 1, y = 0; i <= steps && y < h(); i++) {
    y = i * window.innerHeight;
    window.scrollTo({ top: y, left: 0, behavior: "instant" });
    await new Promise((r) => setTimeout(r, 40));
  }
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });
}
"""


@cache
def _script(name: str) -> str:
    return Path(__file__).with_name(name).read_text(encoding="utf-8")


def extract_script() -> str:
    """The in-page extractor (`extract.js`)."""
    return _script("extract.js")


def dismiss_cookie_banner(page: Page) -> bool:
    """Click an obvious "accept" button inside a cookie/consent banner, if there is one."""
    try:
        clicked = bool(page.evaluate(_script("cookies.js")))
    except PlaywrightError as exc:
        log.debug("cookie banner check failed: %s", exc)
        return False
    if clicked:
        page.wait_for_timeout(300)
    return clicked


def _settle(page: Page) -> None:
    """Scroll through the page so lazy content loads, then wait briefly for the network."""
    try:
        page.evaluate(_LAZY_LOAD_JS, LAZY_LOAD_STEPS)
        page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
    except PlaywrightError:
        pass  # a busy page (polling, analytics) never goes idle; measure what is there


def _screenshot(page: Page, width: int, page_height: float) -> bytes:
    height = min(int(page_height), MAX_SCREENSHOT_HEIGHT_PX)
    return page.screenshot(
        full_page=True,
        type="png",
        clip={"x": 0, "y": 0, "width": width, "height": height},
        animations="disabled",
        caret="hide",
    )


def capture(
    page: Page, viewports: dict[Viewport, ViewportSize] | None = None
) -> tuple[RenderSnapshot, dict[Viewport, bytes]]:
    """Measure every text block and take a full-page PNG in each viewport of a loaded page."""
    sizes = viewports or VIEWPORTS
    dismiss_cookie_banner(page)
    blocks: dict[Viewport, list[TextBlock]] = {}
    heights: dict[Viewport, float] = {}
    shots: dict[Viewport, bytes] = {}
    for name, size in sizes.items():
        page.set_viewport_size(size)
        _settle(page)
        raw: dict[str, Any] = page.evaluate(
            extract_script(), {"maxBlocks": MAX_BLOCKS, "maxText": MAX_TEXT_CHARS}
        )
        blocks[name] = [TextBlock.model_validate(b) for b in raw["blocks"]]
        heights[name] = float(raw["page_height"])
        shots[name] = _screenshot(page, size["width"], heights[name])
    return RenderSnapshot(viewports=blocks, page_height=heights), shots
