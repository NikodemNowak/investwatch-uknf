"""File imports, analyst submissions, sitemap discovery and optional open datasets."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from investwatch.collectors.base import MemoryCooldown, MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.discovery.cache import MemoryCache
from investwatch.collectors.discovery.commoncrawl import commoncrawl_urls
from investwatch.collectors.discovery.gdelt import gdelt_articles
from investwatch.collectors.discovery.registry_domains import registry_domains
from investwatch.collectors.imports.analyst import submission_item
from investwatch.collectors.imports.file_import import ImportFileError, import_file
from investwatch.collectors.sample import SampleCollector
from investwatch.collectors.site import SiteCollector, internal_links
from investwatch.collectors.sitemap import SitemapUrl, keyword_filter, parse_sitemap
from investwatch.collectors.web import WebCollector
from investwatch.config import Settings

REPO = Path(__file__).resolve().parents[3]
Handler = Callable[[httpx.Request], httpx.Response]


# --- file import ------------------------------------------------------------------------


def test_meta_json_import_keeps_provenance() -> None:
    ads = {"data": [{"id": "42", "page_name": "Broker", "ad_creative_bodies": ["Bonus 500 zł"],
                     "publisher_platforms": ["facebook", "instagram"]}]}  # fmt: skip
    content = json.dumps(ads).encode()
    items = import_file("meta_ads_json", content, filename="ads.json", imported_by="jan")
    assert [i.platform for i in items] == ["facebook", "instagram"]
    raw = items[0].raw or {}
    assert raw["access_mode"] == "file_import" and raw["imported_by"] == "jan"
    assert raw["sha256"] == hashlib.sha256(content).hexdigest()


def test_meta_ad_library_report_csv() -> None:
    csv = (
        b"Page ID,Page name,Disclaimer,Amount spent (PLN),Number of ads in Library\n"
        b"155747967133,XTB Online Investing,XTB S.A.,12345,17\n"
    )
    [item] = import_file("meta_ads_csv", csv)
    assert item.external_id == "report:155747967133"
    assert "Płatnik: XTB S.A." in item.text and "Wydatki: 12345" in item.text


def test_meta_ads_csv_with_ad_rows() -> None:
    csv = "id,page_name,ad_creative_bodies,publisher_platforms\n7,X,Kup teraz|Zysk,instagram\n"
    [item] = import_file("meta_ads_csv", csv.encode())
    assert item.platform == "instagram" and "Kup teraz" in item.text and "Zysk" in item.text


def test_tiktok_and_generic_imports() -> None:
    tiktok = {"data": {"ads": [{"ad": {"id": 1, "title": "Kod BONUS"}, "advertiser": {}}]}}
    [ad] = import_file("tiktok_ccl_json", json.dumps(tiktok).encode())
    assert ad.platform == "tiktok" and ad.text == "Kod BONUS"
    jsonl = '{"url": "https://x.pl/a", "text": "Gwarantowany zysk", "platform": "web"}\n'
    [post] = import_file("uknf_sample", jsonl.encode(), provenance_note="pendrive UKNF")
    assert post.collector == "file_import" and (post.raw or {})["provenance_note"]


@pytest.mark.parametrize(
    ("fmt", "content", "message"),
    [
        ("exe", b"[]", "unknown format"),
        ("uknf_sample", "zażółć".encode("cp1250"), "UTF-8"),
        ("meta_ads_json", b"[]", "no records"),
    ],
)
def test_bad_imports_are_refused(fmt: str, content: bytes, message: str) -> None:
    with pytest.raises(ImportFileError, match=message):
        import_file(fmt, content)


def test_synthetic_fixtures_are_labelled() -> None:
    items = SampleCollector().collect("synthetic")
    assert {i.platform for i in items} >= {"facebook", "tiktok", "youtube"}
    assert all((i.raw or {}).get("synthetic") is True for i in items)


def test_submission_records_the_analyst() -> None:
    item = submission_item(
        "Kod promocyjny ABC", "https://www.instagram.com/p/xyz/", screenshot=b"\x89PNG..."
    )
    assert item.platform == "instagram" and item.collector == "analyst"
    assert (item.raw or {})["access_mode"] == "analyst" and item.screenshots


# --- sitemap and site -------------------------------------------------------------------

SITEMAP_INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://broker.pl/sitemap-pages.xml.gz</loc></sitemap>
</sitemapindex>"""
SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://broker.pl/o-nas</loc></url>
  <url><loc>https://broker.pl/promocja-bonus</loc><lastmod>2026-11-01</lastmod></url>
  <url><loc>https://broker.pl/konto-demo</loc><lastmod>2026-11-20</lastmod></url>
  <url><loc>https://other.pl/promocja</loc></url>
</urlset>"""


def test_parse_sitemap_index_gzip_and_feeds() -> None:
    pages, children = parse_sitemap(SITEMAP_INDEX)
    assert pages == [] and children == ["https://broker.pl/sitemap-pages.xml.gz"]
    pages, _ = parse_sitemap(gzip.compress(SITEMAP))
    assert len(pages) == 4
    rss = b"<rss><channel><item><link>https://b.pl/a</link></item></channel></rss>"
    assert parse_sitemap(rss)[0] == [SitemapUrl("https://b.pl/a")]
    assert parse_sitemap(b"<html>not xml") == ([], [])


def test_keyword_filter_newest_first() -> None:
    pages, _ = parse_sitemap(SITEMAP)
    hits = keyword_filter(pages, ["promocj", "konto"])
    assert [h.loc for h in hits][:2] == [
        "https://broker.pl/konto-demo",
        "https://broker.pl/promocja-bonus",
    ]


def _site_handler(seen: list[str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: *\nAllow: /\nSitemap: https://broker.pl/sitemap.xml"
            )
        if path == "/sitemap.xml":
            return httpx.Response(200, content=SITEMAP_INDEX)
        if path == "/sitemap-pages.xml.gz":
            return httpx.Response(200, content=gzip.compress(SITEMAP))
        if path == "/.well-known/tdmrep.json":
            return httpx.Response(404)
        return httpx.Response(200, text=f"<html lang='pl'><p>Strona {path}</p></html>",
                              headers={"content-type": "text/html"})  # fmt: skip

    return handler


def test_site_collector_follows_robots_sitemaps() -> None:
    settings = Settings(collector_min_interval_s=0, commoncrawl_enabled=False)
    seen: list[str] = []
    fetcher = PoliteFetcher(
        settings,
        MemoryRateLimiter(0),
        httpx.MockTransport(_site_handler(seen)),
        cooldown=MemoryCooldown(),
    )
    web = WebCollector(fetcher, name="site", render=False, guard=lambda u: None, settings=settings)
    items = SiteCollector(fetcher, web, settings=settings).collect("2:broker.pl")
    assert [i.url for i in items] == [
        "https://broker.pl/konto-demo",
        "https://broker.pl/promocja-bonus",
    ]
    assert all(i.collector == "site" and i.fetch_status == "ok" for i in items)
    raw = items[0].raw or {}
    assert raw["access_mode"] == "crawler" and raw["discovered_by"]["method"] == "sitemap"
    assert not any("other.pl" in u for u in seen)


def test_site_refuses_platform_domains() -> None:
    settings = Settings(collector_min_interval_s=0)
    fetcher = PoliteFetcher(
        settings, MemoryRateLimiter(0), httpx.MockTransport(lambda r: httpx.Response(500))
    )
    [item] = SiteCollector(fetcher, settings=settings).collect("facebook.com")
    assert item.fetch_status == "blocked"


def test_internal_links() -> None:
    html = '<a href="/promocja">a</a><a href="https://ext.pl/x">b</a><a href="#top">c</a>'
    assert internal_links(html, "https://broker.pl/") == [
        "https://broker.pl/promocja",
        "https://broker.pl/",
    ]


def test_registry_domains_include_brands() -> None:
    domains = registry_domains("all", Settings(APP_DATA_DIR=str(REPO / "data")))  # type: ignore[call-arg]
    assert "xtb.com" in domains


# --- optional open datasets: soft failures ----------------------------------------------


def test_commoncrawl_5xx_is_an_empty_result() -> None:
    settings = Settings(commoncrawl_index="CC-MAIN-2026-44")
    transport = httpx.MockTransport(lambda r: httpx.Response(504))
    assert (
        commoncrawl_urls("broker.pl", settings=settings, transport=transport, cache=MemoryCache())
        == []
    )


def test_commoncrawl_results_are_cached() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        line = {"url": "https://broker.pl/promocja", "mime": "text/html", "status": "200"}
        return httpx.Response(200, text=json.dumps(line) + "\n")

    settings = Settings(commoncrawl_index="CC-MAIN-2026-44", collector_min_interval_s=0)
    cache = MemoryCache()
    for _ in range(2):
        urls = commoncrawl_urls(
            "broker.pl", settings=settings, transport=httpx.MockTransport(handler), cache=cache
        )
        assert urls == ["https://broker.pl/promocja"]
    assert len(calls) == 1


def test_gdelt_is_off_by_default_and_soft_when_on() -> None:
    assert gdelt_articles("x", settings=Settings()) == []
    transport = httpx.MockTransport(lambda r: httpx.Response(429))
    on = Settings(gdelt_enabled=True)
    assert gdelt_articles("x", settings=on, transport=transport, cache=MemoryCache()) == []
