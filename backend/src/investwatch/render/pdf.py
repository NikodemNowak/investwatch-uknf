"""Print HTML to PDF and screenshot crops in headless Chromium (no network: data URLs only)."""

from __future__ import annotations

import base64
import re
import threading
from collections.abc import Callable

from playwright.sync_api import Page, Route, sync_playwright

from investwatch.core.schemas import BBox, Viewport
from investwatch.reports.pdf import VIEWPORT_WIDTH

CROP_PAD = (32, 36)
CROP_MAX_H = 420
CROP_MAX_W = 760
_CROP_HTML = """<!doctype html><html><body style="margin:0">
<div id="c" style="position:relative;overflow:hidden;width:{w}px;height:{h}px">
<img id="i" src="data:image/png;base64,{data}" style="position:absolute;left:{x}px;top:{y}px;
width:{iw}px">
<div style="position:absolute;left:{bx}px;top:{by}px;width:{bw}px;height:{bh}px;
border:3px solid #dc2626;border-radius:4px;box-sizing:border-box"></div></div></body></html>"""


FIT_SCALES = (1.0, 0.9, 0.8, 0.7)
_PAGE = re.compile(rb"/Type\s*/Page[^s]")


def page_count(pdf: bytes) -> int:
    """Pages of a PDF Chromium wrote (page objects are uncompressed there)."""
    return len(_PAGE.findall(pdf))


class ChromiumPdf:
    """Headless Chromium per call (about a second); calls are serialised."""

    _lock = threading.Lock()

    def _with_page(self, fn: Callable[[Page], bytes]) -> bytes:
        with self._lock, sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page()
                # The report is self-contained: nothing it references may be fetched.
                page.route("**/*", _offline)
                return fn(page)
            finally:
                browser.close()

    def pdf(self, html_doc: str, *, landscape: bool = False, one_page: bool = False) -> bytes:
        """Render `html_doc` to A4 PDF (the document sets its own page size).

        `one_page` shrinks the print scale step by step until the document fits one page.
        """

        def run(page: Page) -> bytes:
            page.set_content(html_doc, wait_until="load")
            out = b""
            for scale in FIT_SCALES if one_page else (1.0,):
                out = page.pdf(
                    prefer_css_page_size=True,
                    print_background=True,
                    landscape=landscape,
                    scale=scale,
                )
                if page_count(out) <= 1:
                    break
            return out

        return self._with_page(run)

    def crop(self, png: bytes, bbox: BBox, viewport: Viewport) -> bytes:
        """Screenshot of a box around `bbox` with the evidence frame drawn on it."""
        data = base64.b64encode(png).decode()
        width = VIEWPORT_WIDTH[viewport]

        def run(page: Page) -> bytes:
            page.set_viewport_size({"width": width, "height": 800})
            page.set_content(f'<img id="i" src="data:image/png;base64,{data}">', wait_until="load")
            natural = page.evaluate(
                "() => [document.getElementById('i').naturalWidth,"
                " document.getElementById('i').naturalHeight]"
            )
            scale = natural[0] / width if natural[0] else 1.0
            page_h = natural[1] / scale
            x, y, w, h = bbox
            left = max(0.0, x - CROP_PAD[0])
            top = max(0.0, y - CROP_PAD[1])
            # Keep the crop narrow enough to print the evidence near its real size.
            right = min(float(width), x + w + CROP_PAD[0], left + CROP_MAX_W)
            bottom = min(page_h, y + h + CROP_PAD[1], top + CROP_MAX_H)
            doc = _CROP_HTML.format(
                w=round(right - left),
                h=round(max(1.0, bottom - top)),
                data=data,
                x=round(-left),
                y=round(-top),
                iw=width,
                bx=round(x - left),
                by=round(y - top),
                bw=round(min(w, right - x)),
                bh=round(h),
            )
            page.set_content(doc, wait_until="load")
            out: bytes = page.locator("#c").screenshot(type="png")
            return out

        return self._with_page(run)


def _offline(route: Route) -> None:
    if route.request.url.startswith(("data:", "about:")):
        route.continue_()
    else:
        route.abort("blockedbyclient")
