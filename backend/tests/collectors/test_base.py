from __future__ import annotations

import time

import httpx
import pytest
from pydantic import ValidationError

from investwatch.collectors.base import (
    MemoryCooldown,
    MemoryRateLimiter,
    PoliteFetcher,
    tdm_reserved_in_html,
    tdmrep_reserves,
    url_rejection,
)
from investwatch.collectors.manual import ManualCollector
from investwatch.config import Settings


def _fetcher(handler, **settings: object) -> PoliteFetcher:  # type: ignore[no-untyped-def]
    cfg = Settings(collector_min_interval_s=0, **settings)  # type: ignore[arg-type]
    return PoliteFetcher(
        cfg, MemoryRateLimiter(0), httpx.MockTransport(handler), cooldown=MemoryCooldown()
    )


def test_rotates_user_agents_and_fetches() -> None:
    agents: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        agents.add(request.headers["user-agent"])
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="<html>ok</html>")

    pool = "InvestWatchBot/1.0 (+a) | Mozilla/5.0 (compatible; InvestWatchBot/1.0; +a)"
    fetcher = _fetcher(handler, collector_user_agents=pool)
    results = [fetcher.fetch(f"http://site.example/p{i}") for i in range(30)]
    assert all(r.fetch_status == "ok" for r in results)
    assert agents == {"InvestWatchBot/1.0 (+a)", "Mozilla/5.0 (compatible; InvestWatchBot/1.0; +a)"}


def test_default_agents_identify_the_bot() -> None:
    agents = Settings(collector_contact_email="iw@example.org").user_agents
    assert len(agents) == 2
    assert all("InvestWatchBot/" in a and "github.com" in a for a in agents)
    assert "iw@example.org" in agents[0]


def test_browser_disguise_is_a_config_error() -> None:
    with pytest.raises(ValidationError):
        Settings(collector_user_agents="Mozilla/5.0 (Windows NT 10.0) Chrome/131.0")


def test_robots_rules_for_investwatchbot_apply() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: InvestWatchBot\nDisallow: /\n\nUser-agent: *\nAllow: /"
            )
        return httpx.Response(200, text="x")

    result = _fetcher(handler).fetch("http://site.example/page")
    assert result.fetch_status == "blocked" and "robots" in (result.error or "")


def test_robots_cannot_be_switched_off() -> None:
    assert "collector_respect_robots" not in Settings.model_fields


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abcdefghijk",
        "https://www.facebook.com/ads/library/?q=x",
        "https://www.tiktok.com/@x",
        "https://www.google.pl/search?q=x",
        "https://html.duckduckgo.com/html/?q=x",
        "https://x.com/someone",
    ],
)
def test_platform_hosts_are_refused_without_a_request(url: str) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="x")

    result = _fetcher(handler).fetch(url)
    assert result.fetch_status == "blocked" and "official API only" in (result.error or "")
    assert calls == []


def test_redirect_to_a_platform_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "site.example" and request.url.path == "/go":
            return httpx.Response(302, headers={"location": "https://www.youtube.com/watch?v=x"})
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="x")

    assert _fetcher(handler).fetch("http://site.example/go").fetch_status == "blocked"


def test_tdm_reservation_header_meta_and_tdmrep() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path == "/.well-known/tdmrep.json":
            return httpx.Response(200, json=[{"location": "/news/*", "tdm-reservation": 1}])
        if path == "/header":
            return httpx.Response(200, text="x", headers={"tdm-reservation": "1"})
        if path == "/meta":
            return httpx.Response(
                200, text='<html><head><meta name="tdm-reservation" content="1"></head></html>'
            )
        return httpx.Response(200, text="<html>ok</html>")

    fetcher = _fetcher(handler)
    for path in ("/header", "/meta", "/news/a"):
        result = fetcher.fetch(f"http://site.example{path}")
        assert result.fetch_status == "blocked" and "TDM" in (result.error or ""), path
    assert fetcher.fetch("http://site.example/offer").fetch_status == "ok"


def test_tdm_helpers() -> None:
    assert tdm_reserved_in_html("<meta content='1' name='tdm-reservation'>")
    assert not tdm_reserved_in_html('<meta name="tdm-reservation" content="0">')
    assert tdmrep_reserves('[{"location": "/*", "tdm-reservation": 1}]', "/a")
    assert not tdmrep_reserves('[{"location": "/b/*", "tdm-reservation": 1}]', "/a")
    assert not tdmrep_reserves("not json", "/a")


def test_refusal_starts_a_cooldown_without_retry() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/.well-known/tdmrep.json"}:
            return httpx.Response(404)
        calls.append(request.url.path)
        return httpx.Response(429, headers={"retry-after": "7200"})

    fetcher = _fetcher(handler, collector_proxy_urls="http://p1:3128,http://p2:3128")
    first = fetcher.fetch("http://site.pl/a")
    second = fetcher.fetch("http://www.site.pl/b")
    assert first.fetch_status == "blocked" and "7200" in (first.error or "")
    assert second.fetch_status == "blocked" and "cooling down" in (second.error or "")
    assert calls == ["/a"]
    assert fetcher.cooldown_left("http://site.pl/") > 3600


def test_crawl_delay_lengthens_the_interval() -> None:
    waits: list[float | None] = []

    class Spy(MemoryRateLimiter):
        def wait(self, domain: str, interval_s: float | None = None) -> None:
            waits.append(interval_s)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 5\nAllow: /")
        return httpx.Response(200, text="x")

    cfg = Settings(collector_min_interval_s=0)
    fetcher = PoliteFetcher(cfg, Spy(0), httpx.MockTransport(handler), cooldown=MemoryCooldown())
    assert fetcher.fetch("http://site.example/a").fetch_status == "ok"
    assert waits == [5.0]
    limiter = MemoryRateLimiter(0)
    start = time.monotonic()
    limiter.wait("d", 0.05)
    limiter.wait("d", 0.05)
    assert time.monotonic() - start >= 0.05


def test_respects_robots_txt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="x")

    fetcher = _fetcher(handler)
    assert fetcher.fetch("http://site.example/private/a").fetch_status == "blocked"
    assert fetcher.fetch("http://site.example/public").fetch_status == "ok"


def test_maps_http_errors() -> None:
    def respond(code: int):  # type: ignore[no-untyped-def]
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path in {"/robots.txt", "/.well-known/tdmrep.json"}:
                return httpx.Response(404)
            return httpx.Response(code)

        return handler

    assert _fetcher(respond(403)).fetch("http://site.example/").fetch_status == "blocked"
    assert _fetcher(respond(500)).fetch("http://site.example/").fetch_status == "error"


def test_rate_limiter_spaces_requests() -> None:
    limiter = MemoryRateLimiter(0.05)
    start = time.monotonic()
    for _ in range(3):
        limiter.wait("site.example")
    assert time.monotonic() - start >= 0.1


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://demo-sites/hidden-risk.html", True),
        ("http://127.0.0.1:8000/api/health", False),
        ("http://localhost/", False),
        ("http://minio:9000/", False),
        ("file:///etc/passwd", False),
        ("ftp://example.com/", False),
    ],
)
def test_url_rejection(url: str, ok: bool) -> None:
    assert (url_rejection(url, ["demo-sites"]) is None) is ok


def test_manual_collector_extracts_page(demo_html: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text=demo_html["hidden-risk.html"])

    [item] = ManualCollector(_fetcher(handler)).collect(
        "http://demo-sites/hidden-risk.html?utm_source=x"
    )
    assert item.fetch_status == "ok"
    assert item.external_id == "http://demo-sites/hidden-risk.html"
    assert "38% rocznie" in item.text
    assert item.lang == "pl" and item.html


def test_fetch_records_its_trace() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 0\nDisallow: /x")
        return httpx.Response(200, text="<html>ok</html>")

    fetcher = _fetcher(handler)
    ok = fetcher.fetch("http://site.example/page")
    assert ok.user_agent and "InvestWatchBot" in ok.user_agent
    assert ok.robots == "allowed" and ok.crawl_delay_s == 0 and ok.elapsed_ms is not None
    assert ok.proxy is None  # direct connection (tests replace the transport)
    refused = fetcher.fetch("http://site.example/x/1")
    assert refused.fetch_status == "blocked" and refused.robots == "disallowed"


def test_proxy_credentials_never_reach_the_trace() -> None:
    from investwatch.collectors.base import redact_proxy

    assert redact_proxy("http://user:secret@proxy.example:3128") == "http://proxy.example:3128"
    assert redact_proxy(None) is None
