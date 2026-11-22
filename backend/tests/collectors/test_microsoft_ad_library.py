"""Microsoft Ad Library API collector, offline with answers recorded on 2026-11-21."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from investwatch.collectors.base import MemoryCooldown, MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.official.microsoft_ad_library import (
    API_URL,
    MemoryCache,
    MicrosoftAdLibraryCollector,
    is_investment_page,
    is_relevant,
    parse_target,
)
from investwatch.collectors.policy import connector_status
from investwatch.collectors.schemas import CollectedItem
from investwatch.config import Settings
from investwatch.pipeline.dedup import to_post

FIXTURES = Path(__file__).parent / "fixtures" / "microsoft_ad_library"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def _settings(**kw: Any) -> Settings:
    base = {
        "collector_min_interval_s": 0,
        "microsoft_ad_library_interval_s": 0,
        "platform_max_items": 24,
        "microsoft_ad_library_follow": 2,
        "microsoft_ad_library_details": 1,
        "microsoft_ad_library_max_wait_s": 0,
    }
    return Settings(**(base | kw))


LANDING = "Forex i CFD: otwórz rachunek u brokera, dźwignia, spread, akcje i ETF."


class FakeWeb:
    """Stands in for the crawler: records the landing pages it was asked for."""

    def __init__(
        self, blocked: set[str] | None = None, texts: dict[str, str] | None = None
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.blocked = blocked or set()
        self.texts = texts or {}

    def page(self, target: str, **provenance: Any) -> CollectedItem:
        self.calls.append((target, provenance))
        status = "blocked" if target in self.blocked else "ok"
        return CollectedItem(
            platform="web",
            collector="web",
            external_id=target,
            url=target,
            author="x",
            text="" if status == "blocked" else self.texts.get(target, LANDING),
            fetch_status=status,
            error="disallowed by robots.txt" if status == "blocked" else None,
            raw={"access_mode": "crawler", **provenance},
        )


def _collector(
    handler: Any, settings: Settings | None = None, web: FakeWeb | None = None
) -> tuple[MicrosoftAdLibraryCollector, list[httpx.Request]]:
    settings = settings or _settings()
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        response: httpx.Response = handler(request)
        return response

    fetcher = PoliteFetcher(
        settings,
        MemoryRateLimiter(0),
        httpx.MockTransport(lambda r: httpx.Response(404)),
        cooldown=MemoryCooldown(),
    )
    collector = MicrosoftAdLibraryCollector(
        fetcher,
        settings=settings,
        transport=httpx.MockTransport(record),
        cache=MemoryCache(),
        web=web or FakeWeb(),
    )
    return collector, seen


def _recorded(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/Ads"):
        return httpx.Response(200, json=_load("search_forex.json"))
    if request.url.path.endswith("/Ads/72430624539336"):
        return httpx.Response(200, json=_load("ad_72430624539336.json"))
    return httpx.Response(404, json={"error": {"message": "not found"}})


def test_parse_target() -> None:
    assert parse_target("24:forex", 5) == ("search", "forex", 24, True)
    assert parse_target("forex", 5) == ("search", "forex", 5, True)
    assert parse_target("advertiser:4295011546", 5) == ("advertiser", "4295011546", 5, True)
    assert parse_target("3:XTB relevant=false", 5) == ("search", "XTB", 3, False)


def test_relevance_filter_drops_unrelated_ads() -> None:
    assert is_relevant({"Title": "Online Forex CFD Trading", "AdvertiserName": "FxPro"})
    reel = {"Title": "Shimano Aerlex XTB reel", "DestinationUrl": "https://anglingdirect.co.uk/"}
    assert not is_relevant(reel)
    fluid = {"Title": "FEM CFD Simulation Workstation", "AdvertiserName": "primeLine Solutions"}
    assert not is_relevant(fluid)


def test_search_maps_ads_with_provenance_and_details() -> None:
    collector, seen = _collector(_recorded)
    items = collector.collect("24:forex")
    ads = [i for i in items if i.collector == "microsoft_ad_library"]
    assert len(ads) >= 8 and all(is_relevant(a.raw["data"]) for a in ads)  # type: ignore[index]
    query = seen[0].url.params
    assert query["searchText"] == "forex" and query["countryCodes"] == "151"
    assert query["top"] == "24" and "InvestWatchBot" in seen[0].headers["User-Agent"]
    fxpro = ads[0]
    assert fxpro.platform == "bing" and fxpro.external_id == "72430624539336"
    assert fxpro.url == f"{API_URL}/Ads/72430624539336"
    assert fxpro.author == "FxPro Financial Services Ltd"
    assert "74% of retail CFD accounts lose money" in fxpro.text
    assert fxpro.published_at is not None and fxpro.published_at.year == 2023
    raw = fxpro.raw or {}
    assert raw["access_mode"] == "official_api" and raw["collector"] == "microsoft_ad_library"
    assert raw["destination_url"] == "https://promo.fxpro.com/en/promo-forex"
    assert raw["impression_share_pl"] == "2.5%" and raw["paid_for_by"]
    assert raw["data"]["AdId"] == 72430624539336
    assert "fxpro.com" in raw["candidate_domains"]
    # Only one detail call (MICROSOFT_AD_LIBRARY_DETAILS=1) and no other Microsoft host.
    assert [r.url.path for r in seen].count("/api/v1/Ads/72430624539336") == 1
    assert all(r.url.host == "adlibrary.api.bingads.microsoft.com" for r in seen)
    post = to_post(fxpro)
    assert post.provenance is not None and post.provenance.access_mode == "official_api"
    assert not post.provenance.synthetic


def test_landing_pages_go_through_the_crawler_and_blocks_are_kept() -> None:
    web = FakeWeb(blocked={"https://promo.fxpro.com/en/promo-forex"})
    collector, _ = _collector(_recorded, web=web)
    items = collector.collect("24:forex")
    landing = [i for i in items if i.collector == "web"]
    assert len(landing) == 2 == len(web.calls)
    target, prov = web.calls[0]
    assert target == "https://promo.fxpro.com/en/promo-forex"
    assert prov["discovered_by"] == "microsoft_ad_library" and prov["ad_id"] == "72430624539336"
    assert landing[0].fetch_status == "blocked" and "robots" in (landing[0].error or "")


def test_landing_page_outside_investing_is_dropped() -> None:
    """An ad that matched "CFD" can lead to a protein catalogue or a camera bag shop."""
    camera = "Lowepro TopLoader 65 AW camera bag. Trade in your gear, free delivery, used kit."
    web = FakeWeb(texts={"https://promo.fxpro.com/en/promo-forex": camera})
    collector, _ = _collector(_recorded, web=web)
    landing = [i for i in collector.collect("24:forex") if i.collector == "web"]
    assert [i.url for i in landing] == [web.calls[1][0]]
    assert is_investment_page(LANDING) and not is_investment_page(camera)
    assert not is_investment_page("Factor D CFD protein, recombinant human, 98% purity.")


def test_throttle_falls_back_to_cache_then_reports_blocked() -> None:
    answers = iter([httpx.Response(200, json=_load("search_cfd.json"))])

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Ads"):
            return next(answers, httpx.Response(429, text="<html>too many</html>"))
        return httpx.Response(429)

    settings = _settings(microsoft_ad_library_details=0, microsoft_ad_library_follow=0)
    collector, _ = _collector(flaky, settings)
    first = collector.collect("5:CFD")
    assert len(first) == 5 and all(i.fetch_status == "ok" for i in first)
    assert all("cached_at" not in (i.raw or {}) for i in first)
    # A fresh collector shares nothing but the cache; the API now throttles.
    second = MicrosoftAdLibraryCollector(
        PoliteFetcher(settings, MemoryRateLimiter(0), cooldown=MemoryCooldown()),
        settings=settings,
        transport=httpx.MockTransport(flaky),
        cache=collector._cache,
        web=FakeWeb(),
    )
    again = second.collect("5:CFD")
    assert [i.external_id for i in again] == [i.external_id for i in first]
    assert all((i.raw or {}).get("cached_at") for i in again)
    third, _ = _collector(flaky, settings)
    blocked = third.collect("5:CFD")
    assert len(blocked) == 1 and blocked[0].fetch_status == "blocked"


def test_empty_answer_is_not_an_error() -> None:
    collector, _ = _collector(lambda r: httpx.Response(200, json={"value": []}))
    assert collector.collect("kryptowaluty") == []


def test_bad_request_becomes_an_error_item() -> None:
    error = {"error": {"message": "The limit of '24' for Top query has been exceeded."}}
    collector, _ = _collector(lambda r: httpx.Response(400, json=error))
    [item] = collector.collect("forex")
    assert item.fetch_status == "error" and "24" in (item.error or "")


def test_connector_is_ready_without_a_key() -> None:
    info = connector_status("microsoft_ad_library", Settings())
    assert info is not None and info.status == "ready" and info.access_mode == "official_api"
    off = connector_status("microsoft_ad_library", Settings(microsoft_ad_library_enabled=False))
    assert off is not None and off.status == "disabled"


def test_short_throttle_is_waited_out_and_retried() -> None:
    answers = iter([httpx.Response(429, headers={"Retry-After": "1"})])

    def once_throttled(request: httpx.Request) -> httpx.Response:
        return next(answers, httpx.Response(200, json=_load("search_cfd.json")))

    settings = _settings(
        microsoft_ad_library_details=0,
        microsoft_ad_library_follow=0,
        microsoft_ad_library_max_wait_s=5,
    )
    collector, seen = _collector(once_throttled, settings)
    items = collector.collect("3:CFD")
    assert len(seen) == 2 and len(items) == 3
    assert all(i.fetch_status == "ok" for i in items)
