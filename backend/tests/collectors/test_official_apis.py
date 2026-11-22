"""Offline tests for the official-API collectors (mocked transports, no network)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from croniter import croniter

from investwatch.collectors.base import MemoryCooldown, MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.official.meta_ads_api import (
    MetaAdLibraryCollector,
    meta_platforms,
    parse_target,
)
from investwatch.collectors.official.tiktok_ccl_api import TikTokCommercialContentCollector
from investwatch.collectors.official.youtube_api import (
    MemoryQuota,
    YouTubeApiCollector,
    video_id,
)
from investwatch.collectors.official.youtube_api import parse_target as yt_target
from investwatch.collectors.platform import (
    candidate_domains,
    classify_error,
    extract_links,
    split_limit,
)
from investwatch.collectors.registry import COLLECTORS
from investwatch.collectors.seeds import load_seed_sources
from investwatch.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


def _settings(**kw: Any) -> Settings:
    return Settings(**({"collector_min_interval_s": 0, "platform_max_items": 3} | kw))


def _fetcher(settings: Settings) -> PoliteFetcher:
    return PoliteFetcher(
        settings,
        MemoryRateLimiter(0),
        httpx.MockTransport(lambda r: httpx.Response(404)),
        cooldown=MemoryCooldown(),
    )


# --- shared helpers ---------------------------------------------------------------------


def test_split_limit() -> None:
    assert split_limit("3:kod promocyjny XTB", 5) == (3, "kod promocyjny XTB")
    assert split_limit("kod promocyjny XTB", 5) == (5, "kod promocyjny XTB")
    assert split_limit("https://example.com:443/a", 5) == (5, "https://example.com:443/a")


def test_links_and_candidate_domains() -> None:
    text = "Konto: https://link-pso.xtb.com/pso/abc. Kanał https://youtube.com/@x i bit.ly"
    links = extract_links(text)
    assert links == ["https://link-pso.xtb.com/pso/abc", "https://youtube.com/@x"]
    assert candidate_domains(links) == ["xtb.com"]


def test_classify_error() -> None:
    assert classify_error("HTTP Error 429: Too Many Requests") == "blocked"
    assert classify_error("Unable to extract JSON") == "error"


# --- YouTube Data API v3 ----------------------------------------------------------------

VIDEO = {
    "id": "ya9Q0A8UB4U",
    "snippet": {
        "title": "Kod Referencyjny XTB",
        "description": "Załóż konto: https://link-pso.xtb.com/pso/abc #reklama",
        "tags": ["xtb", "kod"],
        "channelId": "UCFVtJdIJkgYxNfaRIqNOs9Q",
        "channelTitle": "STARTXTB",
        "publishedAt": "2025-04-17T20:22:21Z",
        "defaultAudioLanguage": "pl",
    },
}


def _youtube_api(requests: list[httpx.Request], **responses: Any) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        resource = request.url.path.rsplit("/", 1)[-1]
        if resource in responses:
            value = responses[resource]
            return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
        return httpx.Response(404)

    return handler


def _youtube(handler: Handler, **kw: Any) -> YouTubeApiCollector:
    settings = _settings(youtube_api_key="SECRET-KEY", **kw)
    return YouTubeApiCollector(
        _fetcher(settings),
        settings=settings,
        transport=httpx.MockTransport(handler),
        quota=MemoryQuota(),
    )


def test_youtube_search_then_details() -> None:
    requests: list[httpx.Request] = []
    handler = _youtube_api(
        requests,
        search={"items": [{"id": {"videoId": "ya9Q0A8UB4U"}}]},
        videos={"items": [VIDEO]},
    )
    [item] = _youtube(handler).collect("search:2:XTB kod promocyjny")
    search, videos = requests
    assert search.url.params["regionCode"] == "PL"
    assert search.url.params["q"] == "XTB kod promocyjny"
    assert search.url.params["maxResults"] == "2"
    assert videos.url.params["id"] == "ya9Q0A8UB4U"
    assert all("InvestWatchBot" in r.headers["user-agent"] for r in requests)
    assert item.platform == "youtube" and item.author == "STARTXTB"
    assert item.author_url == "https://www.youtube.com/channel/UCFVtJdIJkgYxNfaRIqNOs9Q"
    assert "Tagi: xtb, kod" in item.text and item.lang == "pl"
    raw = item.raw or {}
    assert raw["access_mode"] == "official_api" and raw["candidate_domains"] == ["xtb.com"]
    assert "SECRET-KEY" not in json.dumps(raw)


def test_youtube_channel_uses_uploads_playlist() -> None:
    requests: list[httpx.Request] = []
    handler = _youtube_api(
        requests,
        channels={"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]},
        playlistItems={"items": [{"contentDetails": {"videoId": "ya9Q0A8UB4U"}}]},
        videos={"items": [VIDEO]},
    )
    items = _youtube(handler).collect("https://www.youtube.com/@inwestomat")
    assert [i.external_id for i in items] == ["ya9Q0A8UB4U"]
    assert requests[0].url.params["forHandle"] == "@inwestomat"
    assert requests[1].url.params["playlistId"] == "UU1"


def test_youtube_without_key_needs_credentials() -> None:
    settings = _settings()
    [item] = YouTubeApiCollector(_fetcher(settings), settings=settings).collect("search:1:x")
    assert item.fetch_status == "blocked" and "YOUTUBE_API_KEY" in (item.error or "")


def test_youtube_quota_is_a_hard_stop() -> None:
    requests: list[httpx.Request] = []
    collector = _youtube(_youtube_api(requests, search={"items": []}), youtube_daily_units=150)
    assert collector.collect("search:1:a") == []
    [item] = collector.collect("search:1:b")
    assert item.fetch_status == "blocked" and "quota" in (item.error or "")
    assert len(requests) == 1


def test_youtube_quota_exceeded_answer_is_blocked_and_hides_key() -> None:
    error = {"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}}
    handler = _youtube_api([], search=httpx.Response(403, json=error))
    [item] = _youtube(handler).collect("search:1:a")
    assert item.fetch_status == "blocked" and "quota" in (item.error or "")
    assert "SECRET-KEY" not in json.dumps(item.model_dump(mode="json"))


def test_youtube_refresh_reports_removed_videos() -> None:
    handler = _youtube_api([], videos={"items": [VIDEO]})
    items, missing = _youtube(handler).refresh(["ya9Q0A8UB4U", "gone0000000"])
    assert [i.external_id for i in items] == ["ya9Q0A8UB4U"] and missing == ["gone0000000"]


def test_youtube_targets() -> None:
    assert yt_target("ytsearch3:etf", 5) == ("search", "etf", 3)
    assert yt_target("search:etf", 5) == ("search", "etf", 5)
    assert yt_target("https://youtu.be/ya9Q0A8UB4U", 5) == ("video", "ya9Q0A8UB4U", 1)
    assert yt_target("https://www.youtube.com/channel/UC1", 5) == ("channel", "UC1", 5)
    assert video_id("https://www.youtube.com/shorts/ya9Q0A8UB4U") == "ya9Q0A8UB4U"
    assert video_id("https://example.com/watch?v=ya9Q0A8UB4U") is None


# --- Meta Ad Library API ----------------------------------------------------------------


def _meta(handler: Handler, **kw: Any) -> MetaAdLibraryCollector:
    settings = _settings(meta_ad_library_token="SECRET", **kw)
    return MetaAdLibraryCollector(
        _fetcher(settings), settings=settings, transport=httpx.MockTransport(handler)
    )


def test_meta_without_token_needs_credentials_and_never_scrapes() -> None:
    settings = _settings()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    collector = MetaAdLibraryCollector(
        _fetcher(settings), settings=settings, transport=httpx.MockTransport(handler)
    )
    [item] = collector.collect("XTB")
    assert item.fetch_status == "blocked" and "META_AD_LIBRARY_TOKEN" in (item.error or "")
    assert calls == []


def test_meta_api_path_with_token() -> None:
    requests: list[httpx.Request] = []

    def api(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        ad = {
            "id": "111222333",
            "page_id": "155747967133",
            "page_name": "XTB Online Investing",
            "ad_delivery_start_time": "2026-11-03",
            "ad_creative_bodies": ["Zacznij inwestować z XTB"],
            "ad_creative_link_captions": ["xtb.com"],
            "ad_snapshot_url": "https://www.facebook.com/ads/archive/render_ad/?id=1&access_token=SECRET",
            "publisher_platforms": ["instagram"],
            "beneficiary_payers": [{"payer": "XTB S.A.", "beneficiary": "XTB S.A."}],
        }
        return httpx.Response(200, json={"data": [ad]})

    [item] = _meta(api, meta_graph_version="v25.0").collect("XTB")
    request = requests[0]
    params = request.url.params
    assert request.url.path == "/v25.0/ads_archive"
    assert params["search_terms"] == "XTB" and params["ad_reached_countries"] == '["PL"]'
    assert "eu_total_reach" in params["fields"] and params["ad_type"] == "ALL"
    assert item.platform == "instagram"
    assert "Płatnik: XTB S.A." in item.text
    assert (item.raw or {})["access_mode"] == "official_api"
    assert "SECRET" not in json.dumps(item.raw)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"code": 10, "error_subcode": 1357045, "message": "x"}, "tożsamości"),
        ({"code": 190, "message": "expired"}, "token wygasł"),
        ({"code": 613, "message": "too many"}, "rate limit"),
    ],
)
def test_meta_api_errors_are_explained(error: dict[str, Any], expected: str) -> None:
    [item] = _meta(lambda r: httpx.Response(400, json={"error": error})).collect(
        "page:155747967133"
    )
    assert item.fetch_status == "blocked" and expected in (item.error or "")
    assert "SECRET" not in (item.error or "")


def test_meta_rate_limit_starts_cooldown() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"error": {"code": 613}})

    collector = _meta(handler)
    collector.collect("XTB")
    [item] = collector.collect("XTB")
    assert "cooling down" in (item.error or "") and len(calls) == 1


def test_meta_single_ad_points_to_import() -> None:
    [item] = _meta(lambda r: httpx.Response(500)).collect("id:1069448859458332")
    assert item.fetch_status == "error" and "import" in (item.error or "")


def test_meta_helpers() -> None:
    assert parse_target("https://www.facebook.com/ads/library/?id=123456789") == (
        "ad",
        "123456789",
    )
    assert parse_target("page:155747967133") == ("page", "155747967133")
    assert parse_target("kod promocyjny") == ("keywords", "kod promocyjny")
    assert meta_platforms(["FACEBOOK", "INSTAGRAM", "THREADS"]) == ["facebook", "instagram"]
    assert meta_platforms(["INSTAGRAM"]) == ["instagram"]
    assert meta_platforms([]) == ["facebook"]


# --- TikTok Commercial Content API ------------------------------------------------------


def test_tiktok_without_credentials_needs_approval() -> None:
    settings = _settings()
    collector = TikTokCommercialContentCollector(_fetcher(settings), settings=settings)
    [item] = collector.collect("XTB")
    assert item.fetch_status == "blocked" and "TIKTOK_CLIENT_KEY" in (item.error or "")


def test_tiktok_query_and_detail() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v2/oauth/token/":
            return httpx.Response(200, json={"access_token": "TOK", "expires_in": 7200})
        if request.url.path.endswith("/ad/query/"):
            ad = {
                "ad": {"id": 1873831353981330, "first_shown_date": "20261101"},
                "advertiser": {"business_name": "Broker X", "paid_for_by": "Broker X Ltd"},
            }
            return httpx.Response(200, json={"data": {"ads": [ad]}, "error": {"code": "ok"}})
        body = {"ad": {"title": "Kod promocyjny BONUS100", "external_url": "https://brokerx.pl"}}
        return httpx.Response(200, json={"data": body, "error": {"code": "ok"}})

    settings = _settings(tiktok_client_key="K", tiktok_client_secret="S")
    collector = TikTokCommercialContentCollector(
        _fetcher(settings), settings=settings, transport=httpx.MockTransport(handler)
    )
    [item] = collector.collect("2:kod promocyjny")
    token, query, _detail = requests
    assert b"grant_type=client_credentials" in token.content
    assert query.headers["authorization"] == "Bearer TOK"
    body = json.loads(query.content)
    assert body["filters"]["country_code"] == "PL" and body["max_count"] == 2
    assert item.platform == "tiktok" and item.author == "Broker X"
    assert "Kod promocyjny BONUS100" in item.text and "Płatnik: Broker X Ltd" in item.text
    assert (item.raw or {})["candidate_domains"] == ["brokerx.pl"]


# --- seeds ------------------------------------------------------------------------------


def test_seed_sources_are_valid() -> None:
    seeds = load_seed_sources()
    assert len(seeds) >= 8
    assert {s.collector for s in seeds} >= {"youtube", "meta_ad_library", "tiktok", "site"}
    assert len({s.name for s in seeds}) == len(seeds)
    for seed in seeds:
        assert seed.collector in COLLECTORS
        assert croniter.is_valid(seed.cron)
        assert not seed.target.startswith("ytsearch")
    assert {s.module_hint for s in seeds} >= {"m1_third_party_ad", "m2_risk_disclosure"}


def test_export_target_limits() -> None:
    from investwatch.collectors.export import ids_only, with_limit
    from investwatch.collectors.seeds import SeedSource

    def seed(collector: str, target: str) -> SeedSource:
        return SeedSource(name="n", collector=collector, target=target, cron="0 * * * *")

    assert with_limit(seed("youtube", "search:3:etf"), 10) == "search:10:etf"
    assert with_limit(seed("youtube", "ytsearch3:etf"), 10) == "search:10:etf"
    assert with_limit(seed("site", "registry:dom_maklerski"), 10) == "10:registry:dom_maklerski"
    assert with_limit(seed("meta_ad_library", "XTB"), 7) == "7:XTB"
    assert (
        with_limit(seed("youtube", "https://www.youtube.com/@x"), 7) == "https://www.youtube.com/@x"
    )
    row = ids_only({"platform": "youtube", "external_id": "a", "text": "long", "author": "x"})
    assert row["text"] == "" and "author" not in row


def test_youtube_ids_target() -> None:
    assert yt_target("ids:Fu8P_wcaiM0, rM4VUh10mLA,bad", 5) == (
        "ids",
        "Fu8P_wcaiM0,rM4VUh10mLA",
        2,
    )
    with pytest.raises(ValueError):
        yt_target("ids:nope", 5)
