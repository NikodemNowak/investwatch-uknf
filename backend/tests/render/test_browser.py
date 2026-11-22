"""Real Chromium captures of demo-sites pages (skipped where no browser is installed, e.g. CI)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from investwatch.config import Settings
from investwatch.render.browser import BlockedNavigationError, Renderer

pytestmark = pytest.mark.browser

DEMO = Path(__file__).resolve().parents[3] / "demo-sites" / "public"


@pytest.fixture(scope="module")
def renderer() -> Iterator[Renderer]:
    r = Renderer(Settings(render_timeout_s=20))
    try:
        r._ensure_browser()
    except Exception as exc:
        pytest.skip(f"Chromium not available: {exc}")
    yield r
    r.close()


def test_hidden_risk_snapshot(renderer: Renderer) -> None:
    result = renderer.render((DEMO / "hidden-risk.html").as_uri())
    snap = result.snapshot
    assert set(snap.viewports) == {"desktop", "tablet", "phone"}
    for viewport, blocks in snap.viewports.items():
        risk = next(b for b in blocks if b.text.startswith("Kontrakty CFD"))
        assert risk.font_px == 9
        assert risk.in_footer and risk.in_collapsed and not risk.visible
        assert risk.color == "#d6d6d6" and risk.background == "#ffffff"
        assert risk.bbox[2] > 0, "hidden text points at its visible container"
        hero = next(b for b in blocks if b.tag_path.endswith("h1"))
        assert hero.visible and hero.font_px == 44 and not hero.in_footer
        assert hero.color == "#ffffff" and hero.background != "#ffffff"  # gradient behind it
        assert snap.page_height[viewport] >= blocks[-1].bbox[1]
        assert result.screenshots[viewport].startswith(b"\x89PNG")


def test_clipped_and_occluded_blocks(renderer: Renderer, tmp_path: Path) -> None:
    page = tmp_path / "p.html"
    page.write_text(
        """<!doctype html><html lang="pl"><body style="margin:0;font-size:16px">
        <p style="font-size:16px">Treść główna strony z dłuższym tekstem do pomiaru.</p>
        <p id="clip" style="width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          Inwestowanie wiąże się z ryzykiem utraty kapitału.</p>
        <p id="under" style="margin-top:40px">Kapitał jest narażony na ryzyko.</p>
        <div style="position:absolute;top:100px;left:0;width:100%;height:40px;background:#fff">
          Zakładka</div>
        <p style="opacity:.5;color:rgba(0,0,0,.5)">Półprzezroczysty tekst.</p>
        </body></html>""",
        encoding="utf-8",
    )
    blocks = {b.text: b for b in renderer.render(page.as_uri()).snapshot.viewports["desktop"]}
    assert blocks["Inwestowanie wiąże się z ryzykiem utraty kapitału."].clipped
    assert not blocks["Treść główna strony z dłuższym tekstem do pomiaru."].clipped
    assert blocks["Kapitał jest narażony na ryzyko."].occluded
    faded = blocks["Półprzezroczysty tekst."]
    assert faded.opacity == 0.5 and faded.color == "#808080"


def test_guard_blocks_navigation(renderer: Renderer) -> None:
    with pytest.raises(Exception) as info:
        renderer.render("http://127.0.0.1:9/", guard=lambda url: "internal address")
    assert isinstance(info.value, BlockedNavigationError) or "BLOCKED" in str(info.value).upper()
