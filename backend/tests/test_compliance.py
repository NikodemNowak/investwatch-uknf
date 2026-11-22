"""Compliance guard (ADR 0008): fails if a disallowed collector or access path comes back.

Platforms and search engines are reached only through official APIs or imports; the crawler
names itself, obeys robots.txt without an off switch and never touches platform hosts.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import httpx
import pytest

from investwatch.collectors.base import MemoryCooldown, MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.policy import PLATFORM_DOMAINS, connector_infos
from investwatch.collectors.registry import COLLECTORS
from investwatch.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src" / "investwatch"
SOURCES = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.py")}

FORBIDDEN_LITERALS = (
    "html.duckduckgo.com",
    "duckduckgo.com/html",
    "lite.duckduckgo.com",
    "searxng",
    "tiktok.com/@",
    "__UNIVERSAL_DATA_FOR_REHYDRATION__",
    "SIGI_STATE",
    "collated_results",
    "facebook:ads",
    "google.com/search",
    "youtube.com/results",
)
"""Fingerprints of the removed scrapers (search-engine HTML, TikTok pages, Ad Library page)."""

REMOVED_SETTINGS = (
    "collector_respect_robots",
    "meta_ad_library_scrape",
    "youtube_search",
    "youtube_subtitles",
    "search_backend",
    "searxng_url",
    "search_cache_ttl_s",
)

ALLOWED_COLLECTORS = {
    "web": "investwatch.collectors.web",
    "site": "investwatch.collectors.site",
    "manual": "investwatch.collectors.manual",
    "sample": "investwatch.collectors.sample",
    "youtube": "investwatch.collectors.official.youtube_api",
    "meta_ad_library": "investwatch.collectors.official.meta_ads_api",
    "tiktok": "investwatch.collectors.official.tiktok_ccl_api",
    "microsoft_ad_library": "investwatch.collectors.official.microsoft_ad_library",
}


def _imports(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_yt_dlp_anywhere() -> None:
    for path, source in SOURCES.items():
        assert "yt_dlp" not in _imports(source), path
    deps = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"]["dependencies"]
    assert not [d for d in deps if d.lower().startswith(("yt-dlp", "yt_dlp"))]


@pytest.mark.parametrize("literal", FORBIDDEN_LITERALS)
def test_no_scraper_fingerprints(literal: str) -> None:
    offenders = [p.name for p, s in SOURCES.items() if literal.lower() in s.lower()]
    assert offenders == [], f"{literal!r} found in {offenders}"


def test_ad_library_page_is_only_a_permalink() -> None:
    """The Ad Library URL may exist only as the analyst permalink constant, never fetched."""
    hits = [p for p, s in SOURCES.items() if "facebook.com/ads/library" in s]
    assert [p.name for p in hits] == ["meta_ads_api.py"]


def test_only_the_renderer_drives_a_browser() -> None:
    users = [
        p.relative_to(SRC).as_posix() for p, s in SOURCES.items() if "playwright" in _imports(s)
    ]
    # golden/build.py renders local synthetic files (file://) with the production capture code.
    allowed = ("render/", "golden/build.py")
    assert users and all(u.startswith(allowed) for u in users), users


def test_collectors_are_the_compliant_set() -> None:
    assert set(COLLECTORS) == set(ALLOWED_COLLECTORS)
    for name, factory in COLLECTORS.items():
        assert getattr(factory, "__module__", "") == ALLOWED_COLLECTORS[name], name


def test_default_settings_are_compliant() -> None:
    settings = Settings()
    assert settings.user_agents and all("InvestWatchBot" in ua for ua in settings.user_agents)
    for field in REMOVED_SETTINGS:
        assert field not in Settings.model_fields, field


def test_platform_connectors_never_run_without_credentials() -> None:
    infos = {i.name: i for i in connector_infos(Settings())}
    assert infos["youtube"].status == "needs_credentials"
    assert infos["meta_ad_library"].status == "needs_credentials"
    assert infos["tiktok"].status == "needs_approval"
    assert all(
        infos[n].access_mode == "official_api" for n in ("youtube", "meta_ad_library", "tiktok")
    )


@pytest.mark.parametrize("domain", sorted(PLATFORM_DOMAINS | {"google.pl", "google.com"}))
def test_crawler_never_contacts_platform_hosts(domain: str) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network request to {request.url}")

    fetcher = PoliteFetcher(
        Settings(), MemoryRateLimiter(0), httpx.MockTransport(explode), cooldown=MemoryCooldown()
    )
    result = fetcher.fetch(f"https://www.{domain}/some/page")
    assert result.fetch_status == "blocked" and "official API only" in (result.error or "")
