from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import Session

from investwatch.collectors.base import MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.sample import load_render_snapshot
from investwatch.collectors.web import WebCollector, ssrf_guard
from investwatch.config import Settings
from investwatch.db import repo
from investwatch.pipeline.analyze import ingest_item
from investwatch.render.browser import RenderResult
from investwatch.storage.minio import get_store

PNG = b"\x89PNG\r\n\x1a\nfake"


def _settings(**kw: object) -> Settings:
    return Settings(  # type: ignore[arg-type]
        collector_min_interval_s=0, check_allowed_internal_hosts="site.example", **kw
    )


def _fetcher(handler, settings: Settings) -> PoliteFetcher:  # type: ignore[no-untyped-def]
    return PoliteFetcher(
        settings, MemoryRateLimiter(0), httpx.MockTransport(handler), url_guard=ssrf_guard(settings)
    )


def _site(html: str):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    return handler


class FakeRenderer:
    def __init__(self, html: str, fail: bool = False) -> None:
        self.html, self.fail, self.calls = html, fail, []  # type: ignore[var-annotated]

    def render(self, url: str, **kw: object) -> RenderResult:
        self.calls.append((url, kw))
        if self.fail:
            raise RuntimeError("chromium crashed")
        return RenderResult(
            final_url=url,
            html=self.html + "<p>Dodane przez skrypt.</p>",
            snapshot=load_render_snapshot(),
            screenshots={"desktop": PNG, "tablet": PNG, "phone": PNG},
        )


def test_text_only_keeps_header_and_footer(demo_html: dict[str, str]) -> None:
    settings = _settings()
    collector = WebCollector(
        _fetcher(_site(demo_html["ok.html"]), settings), render=False, settings=settings
    )
    [item] = collector.collect("http://site.example/ok.html")
    assert item.fetch_status == "ok" and item.collector == "web"
    assert item.text.startswith("Materiał marketingowy")  # <header>
    assert "Podmiot nadzorowany przez KNF" in item.text  # <footer>
    assert item.render is None and item.screenshots == {}
    assert item.html and "<footer>" in item.html


def test_render_adds_snapshot_screenshots_and_rendered_text(demo_html: dict[str, str]) -> None:
    settings = _settings()
    renderer = FakeRenderer(demo_html["hidden-risk.html"])
    collector = WebCollector(
        _fetcher(_site(demo_html["hidden-risk.html"]), settings),
        renderer,  # type: ignore[arg-type]
        render=True,
        settings=settings,
    )
    [item] = collector.collect("http://site.example/hidden-risk.html")
    assert item.render is not None and set(item.screenshots) == {"desktop", "tablet", "phone"}
    assert "Dodane przez skrypt." in item.text
    assert "Kontrakty CFD" in item.text  # collapsed <details> text stays in the analysed text
    url, kw = renderer.calls[0]
    assert url == "http://site.example/hidden-risk.html" and kw["guard"] is not None


def test_render_failure_falls_back_to_http_text(demo_html: dict[str, str]) -> None:
    settings = _settings()
    collector = WebCollector(
        _fetcher(_site(demo_html["ok.html"]), settings),
        FakeRenderer("", fail=True),  # type: ignore[arg-type]
        render=True,
        settings=settings,
    )
    [item] = collector.collect("http://site.example/ok.html")
    assert item.fetch_status == "ok" and "Fundusz Zrównoważony Plus" in item.text
    assert item.render is None


def test_redirect_to_private_address_is_blocked() -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://127.0.0.1:9000/minio/"})

    settings = _settings()
    collector = WebCollector(_fetcher(handler, settings), render=False, settings=settings)
    [item] = collector.collect("http://site.example/promo")
    assert item.fetch_status == "blocked"
    assert not any("127.0.0.1" in h for h in hits)  # the hop was refused before any request


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:5432/", "file:///etc"])
def test_private_target_is_rejected_without_fetching(url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    settings = _settings()
    collector = WebCollector(_fetcher(handler, settings), render=False, settings=settings)
    assert collector.collect(url)[0].fetch_status == "blocked"


def test_ingest_stores_screenshots_and_snapshot(
    session: Session, demo_html: dict[str, str]
) -> None:
    settings = _settings()
    collector = WebCollector(
        _fetcher(_site(demo_html["hidden-risk.html"]), settings),
        FakeRenderer(demo_html["hidden-risk.html"]),  # type: ignore[arg-type]
        render=True,
        settings=settings,
    )
    [item] = collector.collect("http://site.example/hidden-risk.html")
    post = ingest_item(session, item).post
    stored = repo.get_post(session, post.id)
    assert stored is not None and stored.render_key == f"render/{post.id}.json"
    assert stored.screenshot_keys["phone"] == f"shots/{post.id}/phone.png"
    assert get_store().get_bytes(stored.screenshot_keys["phone"]) == PNG
