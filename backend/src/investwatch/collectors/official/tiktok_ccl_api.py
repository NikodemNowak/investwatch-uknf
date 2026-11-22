"""The `tiktok` collector: TikTok Commercial Content API (ads shown in the EU), nothing else.

Access needs an approved TikTok for Developers application (`TIKTOK_CLIENT_KEY`,
`TIKTOK_CLIENT_SECRET`). Without it the connector reports "wymaga zgody platformy" and does not
run; TikTok pages are never parsed (TikTok's Terms forbid automated extraction).

Flow (developers.tiktok.com, Commercial Content API docs read on 2026-11-21):
1. `POST /v2/oauth/token/` (form: client_key, client_secret, grant_type=client_credentials)
   -> bearer token valid ~2 h, cached in-process.
2. `POST /v2/research/adlib/ad/query/?fields=...` with
   `{"filters": {"ad_published_date_range": {"min", "max"}, "country_code": "PL"},
   "search_term": ..., "max_count": <=10}` -> ad ids, advertiser, dates, reach.
3. `POST /v2/research/adlib/ad/detail/?fields=...` with `{"ad_id": ...}` -> `ad.title`
   (the ad caption, the only text field) and the landing URL.

Not exercised against the live API (access pending); covered by tests on mocked responses.
Docs disagree on `country_code` vs `country_code_list`; both are sent.

Targets: `[N:]<search term>` (at most 50 characters, exact phrase).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from investwatch.collectors.base import PoliteFetcher
from investwatch.collectors.official.http import api_client
from investwatch.collectors.platform import (
    candidate_domains,
    envelope,
    extract_links,
    failed_item,
    join_text,
    split_limit,
)
from investwatch.collectors.schemas import CollectedItem
from investwatch.config import Settings, get_settings

log = logging.getLogger(__name__)

BASE_URL = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{BASE_URL}/oauth/token/"
QUERY_URL = f"{BASE_URL}/research/adlib/ad/query/"
DETAIL_URL = f"{BASE_URL}/research/adlib/ad/detail/"
LIBRARY_URL = "https://library.tiktok.com/ads/detail/"
QUERY_FIELDS = (
    "ad.id,ad.first_shown_date,ad.last_shown_date,ad.status,ad.reach,"
    "advertiser.business_id,advertiser.business_name,advertiser.paid_for_by"
)
DETAIL_FIELDS = "ad.id,ad.title,ad.external_url,ad.call_to_action,advertiser.business_name"
MAX_COUNT = 10
LOOKBACK_DAYS = 360
"""The query's date range must start within the last year."""


class TikTokApiError(RuntimeError):
    """A refused or failed API call (message never contains credentials)."""


def _date(value: Any) -> datetime | None:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=UTC)
    return None


def ad_item(ad: dict[str, Any], target: str, **provenance: Any) -> CollectedItem:
    """Map one CCL ad (`{"ad": {...}, "advertiser": {...}}`, query merged with detail)."""
    info = ad.get("ad") or {}
    advertiser = ad.get("advertiser") or {}
    ad_id = str(info.get("id") or "")
    url = f"{LIBRARY_URL}?ad_id={ad_id}"
    payer = advertiser.get("paid_for_by") or advertiser.get("paid_by")
    landing = info.get("external_url")
    text = join_text(
        str(info.get("title") or ""),
        f"Link: {landing}" if landing else None,
        f"Płatnik: {payer}" if payer else None,
    )
    links = extract_links(text)
    name = str(advertiser.get("business_name") or advertiser.get("business_id") or "?")
    return CollectedItem(
        platform="tiktok",
        collector="tiktok",
        external_id=ad_id,
        url=url,
        author=name,
        author_url=None,
        text=text,
        published_at=_date(info.get("first_shown_date")),
        fetch_status="ok" if text else "no_text",
        raw=envelope(
            "tiktok",
            url,
            target,
            ad,
            paid_for_by=[str(payer)] if payer else [],
            landing_url=landing,
            candidate_domains=candidate_domains(links),
            **provenance,
        ),
    )


class TikTokCommercialContentCollector:
    """Ads from the TikTok Commercial Content API for one search term."""

    name = "tiktok"

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
        self._token: tuple[str, float] | None = None

    def collect(self, target: str) -> list[CollectedItem]:
        """Collect ads for `target`; never raises."""
        settings = self._settings
        if not (settings.tiktok_client_key and settings.tiktok_client_secret):
            return [
                failed_item(
                    self.name,
                    "tiktok",
                    target,
                    "blocked",
                    "wymaga zgody platformy: set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET "
                    "(TikTok Commercial Content API); TikTok pages are never scraped",
                )
            ]
        limit, term = split_limit(target, settings.platform_max_items)
        try:
            ads = self._query(term[:50], min(limit, MAX_COUNT))
            return [ad_item(self._detail(ad), target) for ad in ads]
        except TikTokApiError as exc:
            return [failed_item(self.name, "tiktok", target, "blocked", str(exc))]
        except (httpx.HTTPError, ValueError) as exc:
            return [failed_item(self.name, "tiktok", target, "error", type(exc).__name__)]

    def _access_token(self, client: httpx.Client) -> str:
        if self._token and self._token[1] > time.monotonic():
            return self._token[0]
        response = client.post(
            TOKEN_URL,
            data={
                "client_key": self._settings.tiktok_client_key,
                "client_secret": self._settings.tiktok_client_secret,
                "grant_type": "client_credentials",
            },
        )
        body = response.json() if response.content else {}
        token = body.get("access_token")
        if response.status_code >= 400 or not token:
            raise TikTokApiError(
                f"TikTok token refused: {body.get('error') or response.status_code}"
            )
        expires = float(body.get("expires_in") or 7200)
        self._token = (str(token), time.monotonic() + expires - 60)
        return str(token)

    def _post(self, url: str, fields: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._fetcher.cooldown_left(url) > 0:
            raise TikTokApiError("TikTok API cooling down after a rate limit")
        self._fetcher.wait(url)
        with api_client(self._fetcher, self._settings, self._transport) as client:
            token = self._access_token(client)
            response = client.post(
                url,
                params={"fields": fields},
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        data: dict[str, Any] = response.json() if response.content else {}
        error = data.get("error") or {}
        code = str(error.get("code") or "")
        if response.status_code == 429 or code == "rate_limit_exceeded":
            self._fetcher.start_cooldown(url)
            raise TikTokApiError("TikTok API rate limit; cooling down")
        if response.status_code >= 400 or (code and code != "ok"):
            raise TikTokApiError(
                f"TikTok API HTTP {response.status_code}: {code} {error.get('message') or ''}"[:300]
            )
        return data

    def _query(self, term: str, count: int) -> list[dict[str, Any]]:
        today = datetime.now(UTC).date()
        country = self._settings.meta_ad_library_country
        body = {
            "filters": {
                "ad_published_date_range": {
                    "min": (today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"),
                    "max": today.strftime("%Y%m%d"),
                },
                "country_code": country,
                "country_code_list": [country],
            },
            "search_term": term,
            "max_count": count,
        }
        data = self._post(QUERY_URL, QUERY_FIELDS, body).get("data") or {}
        ads = [a for a in data.get("ads") or [] if isinstance(a, dict)]
        return ads[:count]

    def _detail(self, ad: dict[str, Any]) -> dict[str, Any]:
        ad_id = (ad.get("ad") or {}).get("id")
        if not ad_id:
            return ad
        try:
            detail = self._post(DETAIL_URL, DETAIL_FIELDS, {"ad_id": int(ad_id)}).get("data") or {}
        except TikTokApiError as exc:
            log.info("tiktok ad detail unavailable for %s: %s", ad_id, exc)
            return ad
        return {
            "ad": {**(ad.get("ad") or {}), **(detail.get("ad") or {})},
            "advertiser": {**(ad.get("advertiser") or {}), **(detail.get("advertiser") or {})},
        }
