"""The `meta_ad_library` collector: Facebook/Instagram ads through the Meta Ad Library API only.

The Ad Library is the public ad repository required by DSA art. 39; its API
(`GET graph.facebook.com/<v>/ads_archive`) needs `META_AD_LIBRARY_TOKEN` from an
identity-verified account. Without a token the connector reports "wymaga klucza" and does not
run; there is no fallback to the web page (facebook.com robots.txt and Meta's Terms forbid it).

Targets: `[N:]<keywords>` or `page:<page id>` (or an Ad Library URL with `q=` /
`view_all_page_id=`). The API cannot read a single ad by id: import the Ad Library export
instead (`POST /api/imports`, format `meta_ads_csv` / `meta_ads_json`).
Every ad becomes one post per Meta platform it ran on (Facebook, Instagram).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from investwatch.collectors.base import PoliteFetcher
from investwatch.collectors.official.http import api_client, strip_secrets
from investwatch.collectors.platform import (
    candidate_domains,
    envelope,
    extract_links,
    failed_item,
    from_timestamp,
    join_text,
    split_limit,
)
from investwatch.collectors.schemas import CollectedItem
from investwatch.config import Settings, get_settings
from investwatch.core.schemas import FetchStatus, Platform

log = logging.getLogger(__name__)

LIBRARY_URL = "https://www.facebook.com/ads/library/"
API_FIELDS = (
    "id,page_id,page_name,ad_creation_time,ad_delivery_start_time,ad_delivery_stop_time,"
    "ad_creative_bodies,ad_creative_link_titles,ad_creative_link_descriptions,"
    "ad_creative_link_captions,ad_snapshot_url,publisher_platforms,languages,bylines,"
    "beneficiary_payers,eu_total_reach,target_ages,target_gender,target_locations,"
    "age_country_gender_reach_breakdown"
)
_ID = re.compile(r"^\d{6,25}$")
_RATE_LIMIT_CODES = {4, 17, 32, 613}
_ERRORS = {
    1357045: "konto bez potwierdzonej tożsamości (facebook.com/ID) albo brak dostępu do API",
    190: "token wygasł lub jest nieprawidłowy (META_AD_LIBRARY_TOKEN)",
    10: "aplikacja nie ma dostępu do Ad Library API",
}


def ad_url(ad_id: str) -> str:
    """Public Ad Library permalink of one ad (a link for the analyst, never fetched)."""
    return f"{LIBRARY_URL}?id={ad_id}"


def graph_url(settings: Settings) -> str:
    """`ads_archive` endpoint for the configured Graph API version."""
    return f"https://graph.facebook.com/{settings.meta_graph_version}/ads_archive"


def parse_target(target: str) -> tuple[str, str]:
    """Return (kind, value): kind is `ad` (not supported by the API), `page` or `keywords`."""
    value = target.strip()
    if value.lower().startswith(("http://", "https://")):
        ids = parse_qs(urlsplit(value).query)
        if ids.get("id"):
            return "ad", ids["id"][0]
        if ids.get("view_all_page_id"):
            return "page", ids["view_all_page_id"][0]
        if ids.get("q"):
            return "keywords", ids["q"][0]
    lowered = value.lower()
    if lowered.startswith("id:") and _ID.match(value[3:].strip()):
        return "ad", value[3:].strip()
    if lowered.startswith("page:") and _ID.match(value[5:].strip()):
        return "page", value[5:].strip()
    return "keywords", value


def meta_platforms(platforms: list[str]) -> list[Platform]:
    """Our platforms for an ad's `publisher_platforms`: one post per Facebook / Instagram.

    Messenger, Audience Network and Threads placements are Facebook-operated surfaces and count
    as Facebook; an ad without the field is attributed to Facebook.
    """
    upper = {p.upper() for p in platforms}
    result: list[Platform] = []
    if upper - {"INSTAGRAM"} or not upper:
        result.append("facebook")
    if "INSTAGRAM" in upper:
        result.append("instagram")
    return result


def _published(value: Any) -> datetime | None:
    published = from_timestamp(value)
    if published is None and isinstance(value, str) and value:
        try:
            published = datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
        except ValueError:
            published = None
    return published


def ad_items(
    ad: dict[str, Any], target: str, *, collector: str = "meta_ad_library", **provenance: Any
) -> list[CollectedItem]:
    """Map one `ads_archive` record (API answer or Ad Library export) to items."""
    ad_id = str(ad.get("id") or ad.get("ad_archive_id") or "")
    url = ad_url(ad_id)
    platforms = [str(p) for p in ad.get("publisher_platforms") or []]
    payers = [
        str(p.get("payer") or p.get("beneficiary") or "")
        for p in ad.get("beneficiary_payers") or []
        if isinstance(p, dict)
    ]
    payers += [str(b) for b in ad.get("bylines") or []]
    bodies = list(dict.fromkeys(ad.get("ad_creative_bodies") or []))
    titles = list(dict.fromkeys(ad.get("ad_creative_link_titles") or []))
    descriptions = list(dict.fromkeys(ad.get("ad_creative_link_descriptions") or []))
    captions = list(dict.fromkeys(ad.get("ad_creative_link_captions") or []))
    text = join_text(
        *bodies,
        *titles,
        *descriptions,
        "Link: " + ", ".join(captions) if captions else None,
        "Płatnik: " + ", ".join(p for p in payers if p) if any(payers) else None,
        "Platformy: " + ", ".join(platforms) if platforms else None,
    )
    data = dict(ad)
    if data.get("ad_snapshot_url"):
        data["ad_snapshot_url"] = strip_secrets(str(data["ad_snapshot_url"]))
    links = extract_links(text)
    page_id = str(ad.get("page_id") or "")
    raw = envelope(
        collector,
        url,
        target,
        data,
        paid_for_by=[p for p in payers if p],
        snapshot_url=data.get("ad_snapshot_url"),
        candidate_domains=candidate_domains(links + [f"https://{c}" for c in captions]),
        publisher_platforms=platforms,
        **provenance,
    )
    item = CollectedItem(
        platform="facebook",
        collector=collector,
        external_id=ad_id,
        url=url,
        author=str(ad.get("page_name") or page_id or "?"),
        author_url=f"https://www.facebook.com/{page_id}" if page_id else None,
        text=text,
        lang=None,
        published_at=_published(ad.get("ad_delivery_start_time")),
        fetch_status="ok" if text else "no_text",
        raw=raw,
    )
    return [item.model_copy(update={"platform": p}) for p in meta_platforms(platforms)]


class MetaAdLibraryCollector:
    """Ads from the Meta Ad Library API for keywords or a page id."""

    name = "meta_ad_library"

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        *,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Tests inject the HTTP transport."""
        self._settings = settings or get_settings()
        self._fetcher = fetcher or PoliteFetcher(self._settings)
        self._transport = transport

    def collect(self, target: str) -> list[CollectedItem]:
        """Collect ads for `target`; never raises."""
        if not self._settings.meta_ad_library_token:
            return [
                failed_item(
                    self.name,
                    "facebook",
                    target,
                    "blocked",
                    "wymaga klucza: set META_AD_LIBRARY_TOKEN (Meta Ad Library API); "
                    "the Ad Library web page is never scraped",
                )
            ]
        limit, rest = split_limit(target, self._settings.platform_max_items)
        kind, value = parse_target(rest)
        if kind == "ad":
            return [
                failed_item(
                    self.name,
                    "facebook",
                    target,
                    "error",
                    "the Ad Library API cannot read one ad by id; import the Ad Library export",
                )
            ]
        try:
            return self._api(kind, value, limit, target)
        except Exception as exc:  # a broken source must not crash the scrape run
            log.warning("meta ad library failed for %r: %s", target, type(exc).__name__)
            return [failed_item(self.name, "facebook", target, "error", type(exc).__name__)]

    def _api(self, kind: str, value: str, limit: int, target: str) -> list[CollectedItem]:
        url = graph_url(self._settings)
        left = self._fetcher.cooldown_left(url)
        if left > 0:
            error = f"Ad Library API rate limit; cooling down ({left:.0f} s)"
            return [failed_item(self.name, "facebook", target, "blocked", error)]
        params: dict[str, str | int] = {
            "access_token": self._settings.meta_ad_library_token,
            "ad_reached_countries": json.dumps([self._settings.meta_ad_library_country]),
            "ad_active_status": "ALL",
            "ad_type": self._settings.meta_ad_type,
            "fields": API_FIELDS,
            "limit": limit,
        }
        if kind == "page":
            params["search_page_ids"] = json.dumps([value])
        else:
            params["search_terms"] = value
            params["search_type"] = "KEYWORD_UNORDERED"
        self._fetcher.wait(url)
        with api_client(self._fetcher, self._settings, self._transport) as client:
            try:
                response = client.get(url, params=params)
            except httpx.HTTPError as exc:
                # The request URL carries the token: report only the error type.
                return [failed_item(self.name, "facebook", target, "error", type(exc).__name__)]
        if response.status_code >= 400:
            return [self._error(response, url, target)]
        ads = response.json().get("data", [])
        return [item for ad in ads[:limit] for item in ad_items(ad, target)]

    def _error(self, response: httpx.Response, url: str, target: str) -> CollectedItem:
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        code = int(error.get("code") or 0)
        subcode = int(error.get("error_subcode") or 0)
        message = str(error.get("message") or "")[:300]
        status: FetchStatus = "blocked" if response.status_code in {401, 403, 429} else "error"
        if code in _RATE_LIMIT_CODES:
            self._fetcher.start_cooldown(url)
            status, message = "blocked", f"rate limit (code {code}); cooling down"
        elif subcode in _ERRORS or code in _ERRORS:
            status, message = "blocked", _ERRORS.get(subcode) or _ERRORS[code]
        text = f"Ad Library API HTTP {response.status_code}: {message}"[:500]
        return failed_item(self.name, "facebook", target, status, text)
