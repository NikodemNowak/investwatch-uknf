"""The `microsoft_ad_library` collector: Bing ads through the Microsoft Ad Library API.

The Ad Library is Microsoft Advertising's public ad repository for the EEA (DSA art. 39). Its
REST API (`GET https://adlibrary.api.bingads.microsoft.com/api/v1/Ads`) is public: no sign-up,
no key, stricter limits for unauthenticated calls (at most 24 ads per call; a burst of calls
answers 429). Microsoft's guide names researchers and regulators as its users. Nothing else is
fetched from Microsoft or Bing; the bing.com pages stay on the crawler's deny-list.

Targets: `[N:]<search text>` (e.g. `24:forex`) or `advertiser:<id>`. Per run:

1. `Ads?searchText=...&countryCodes=151` (Poland), paged by 24 with `skip`;
2. ads whose text has nothing to do with investing are dropped (the search also matches
   e.g. fishing reels for "XTB"); `relevant=false` in the target turns the filter off;
3. `Ads/{id}?expand=AdDetails(...)` for the first `MICROSOFT_AD_LIBRARY_DETAILS` ads: start
   and end date, who paid, impressions by country (the list call has none of these);
4. the landing page (`DestinationUrl`) of the first `MICROSOFT_AD_LIBRARY_FOLLOW` ads goes to
   the `web` crawler, which applies robots.txt, TDM reservations and the rate limit; a refusal
   is stored as a `blocked` item with the reason.

Calls are `MICROSOFT_AD_LIBRARY_INTERVAL_S` apart; answers are cached
(`MICROSOFT_AD_LIBRARY_CACHE_TTL_S`), and an empty or throttled answer falls back to the cached
one, so a throttled run neither fails nor wipes what the analyst saw.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import UTC, datetime
from functools import cache
from typing import Any, Protocol

import httpx
import redis

from investwatch.collectors.base import PoliteFetcher, retry_after_s
from investwatch.collectors.official.http import api_client
from investwatch.collectors.platform import (
    candidate_domains,
    envelope,
    failed_item,
    join_text,
    split_limit,
)
from investwatch.collectors.schemas import CollectedItem
from investwatch.config import Settings, get_settings
from investwatch.core.schemas import FetchStatus

log = logging.getLogger(__name__)

API_URL = "https://adlibrary.api.bingads.microsoft.com/api/v1"
GUIDE_URL = "https://learn.microsoft.com/en-us/advertising/guides/ad-library-api?view=bingads-13"
PAGE = 24
"""Largest `top` the API accepts without authentication."""
DETAILS_EXPAND = "AdDetails(expand=ImpressionsByCountry,Targets)"
THROTTLE_COOLDOWN_S = 90.0
"""Pause after a 429 without `Retry-After` (the limit is per minute, not per hour)."""

_FINANCE = re.compile(
    r"forex|\bfx\b|\bcfds?\b|trad(?:e|ing|er)|broker|inwest|invest|akcj|stock|share|etf|"
    r"krypto|crypto|bitcoin|\bbtc\b|giełd|gield|zysk|profit|lewar|leverage|spread|"
    r"opcj|option|obligac|bond|fundusz|fund\b|portfel|portfolio|dywidend|dividend|"
    r"maklersk|brokerage|lose money|traci pieniądze|kapitał|capital",
    re.I,
)
_NOT_FINANCE = re.compile(
    r"fluid|strömung|simulation|\bfem\b|forex[- ]?(?:platte|plaat|board|druck)|met foto|"
    r"for dummies|reel|angel",
    re.I,
)
"""Same words, other trades: CFD as fluid dynamics, Forex as a PVC board, books, fishing."""
_ADVERTISER = re.compile(r"^advertiser:(\d{1,20})$", re.I)


class ResponseCache(Protocol):
    """Cached API answers, shared by every worker when Redis is available."""

    def get(self, key: str) -> str | None:
        """The cached value, or None."""
        ...

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store `value` for `ttl_s` seconds."""
        ...


class MemoryCache:
    """Per-process cache (tests, eager mode)."""

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        """The value unless it expired."""
        with self._lock:
            hit = self._data.get(key)
        return hit[1] if hit and hit[0] > time.monotonic() else None

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store with an expiry."""
        with self._lock:
            self._data[key] = (time.monotonic() + ttl_s, value)


class RedisCache:
    """`iw:cache:msads:<sha1>` keys with a TTL."""

    def __init__(self, client: redis.Redis) -> None:
        """Use `client`."""
        self._client = client

    def get(self, key: str) -> str | None:
        """The value, or None."""
        value = self._client.get(f"iw:cache:msads:{key}")
        return value.decode() if isinstance(value, bytes) else None

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store with a TTL."""
        self._client.setex(f"iw:cache:msads:{key}", ttl_s, value)


@cache
def get_cache() -> ResponseCache:
    """Return the answer cache for this process."""
    settings = get_settings()
    if settings.celery_eager or settings.realtime_backend == "memory":
        return MemoryCache()
    return RedisCache(redis.Redis.from_url(settings.redis_url))


class AdLibraryError(RuntimeError):
    """A call failed; `throttled` when the API asked us to slow down."""

    def __init__(self, message: str, *, throttled: bool = False) -> None:
        """Keep whether it was a throttle."""
        super().__init__(message)
        self.throttled = throttled


def ad_url(ad_id: str) -> str:
    """The ad's record in the API (the analyst's link back to the official repository)."""
    return f"{API_URL}/Ads/{ad_id}"


def parse_target(target: str, default: int) -> tuple[str, str, int, bool]:
    """Return (kind, value, limit, relevant_only); kind is `search` or `advertiser`."""
    value = target.strip()
    relevant = True
    if value.lower().endswith(" relevant=false"):
        value, relevant = value[: -len(" relevant=false")].rstrip(), False
    limit, value = split_limit(value, default)
    match = _ADVERTISER.match(value)
    if match:
        return "advertiser", match.group(1), limit, relevant
    return "search", value, limit, relevant


def is_relevant(ad: dict[str, Any]) -> bool:
    """Does the ad advertise something investment-related (not a reel called "XTB")?"""
    text = " ".join(
        str(ad.get(k) or "")
        for k in ("AdvertiserName", "Title", "Description", "DisplayUrl", "DestinationUrl")
    )
    return bool(_FINANCE.search(text)) and not _NOT_FINANCE.search(text)


_INVESTMENT_TERMS = re.compile(
    r"forex|\bcfds?\b|broker|inwest|invest|akcj|\bstocks?\b|\betfs?\b|krypto|crypto|bitcoin|"
    r"giełd|gield|obligac|\bbonds?\b|lewar|leverage|spread|maklersk|brokerage|dywidend|"
    r"dividend|portfel|portfolio|rachun\w* (?:inwest|maklersk)|trading account|fundusz",
    re.I,
)
LANDING_MIN_TERMS = 3
"""Distinct investment words a followed landing page needs; fewer means it is off topic."""


def is_investment_page(text: str) -> bool:
    """Is a landing page about investing (not a camera shop that offers a "trade-in")?"""
    found = {m.group(0).casefold()[:5] for m in _INVESTMENT_TERMS.finditer(text)}
    return len(found) >= LANDING_MIN_TERMS


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=UTC)
    except ValueError:
        return None


def poland_share(details: dict[str, Any]) -> str | None:
    """Share of impressions served in Poland (e.g. "2.5%"), when the API reports it."""
    for row in details.get("ImpressionsByCountry") or []:
        if isinstance(row, dict) and str(row.get("Country")) in {"Poland", "Polska"}:
            return str(row.get("ImpressionShare") or "") or None
    return None


def ad_item(ad: dict[str, Any], target: str, **provenance: Any) -> CollectedItem:
    """Map one Ad Library record (with `AdDetails` when read) to a post."""
    ad_id = str(ad.get("AdId") or "")
    details = ad.get("AdDetails") if isinstance(ad.get("AdDetails"), dict) else {}
    assert isinstance(details, dict)
    advertiser = str(ad.get("AdvertiserName") or "").strip()
    advertiser_id = str(ad.get("AdvertiserId") or "")
    payer = str(details.get("PaidForByName") or "").strip()
    display = str(ad.get("DisplayUrl") or "").strip()
    destination = str(ad.get("DestinationUrl") or "").strip()
    share = poland_share(details)
    text = join_text(
        str(ad.get("Title") or ""),
        str(ad.get("Description") or ""),
        f"Link: {display}" if display else None,
        f"Reklamodawca: {advertiser}" if advertiser else None,
        f"Płatnik: {payer}" if payer and payer != advertiser else None,
    )
    links = [destination] if destination else []
    if display:
        links.append(f"https://{display.split('/')[0]}")
    url = ad_url(ad_id)
    return CollectedItem(
        platform="bing",
        collector="microsoft_ad_library",
        external_id=ad_id,
        url=url,
        author=advertiser or advertiser_id or "?",
        author_url=f"{API_URL}/Advertisers/{advertiser_id}" if advertiser_id else None,
        text=text,
        lang=None,
        published_at=_date(details.get("StartDate")),
        fetch_status="ok" if text else "no_text",
        raw=envelope(
            "microsoft_ad_library",
            url,
            target,
            ad,
            advertiser=advertiser or None,
            paid_for_by=payer or None,
            destination_url=destination or None,
            start_date=details.get("StartDate"),
            end_date=details.get("EndDate"),
            impressions=details.get("TotalImpressionsRange"),
            impression_share_pl=share,
            candidate_domains=candidate_domains(links),
            terms_url=GUIDE_URL,
            **provenance,
        ),
    )


class MicrosoftAdLibraryCollector:
    """Ads served in Poland from the Microsoft Ad Library API, plus their landing pages."""

    name = "microsoft_ad_library"

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        *,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache | None = None,
        web: Any | None = None,
    ) -> None:
        """Tests inject the transport, the cache and the landing-page crawler (`web`)."""
        self._settings = settings or get_settings()
        self._fetcher = fetcher or PoliteFetcher(self._settings)
        self._transport = transport
        self._cache = cache or get_cache()
        self._web = web

    def collect(self, target: str) -> list[CollectedItem]:
        """Ads for `target` and their landing pages; never raises."""
        if not self._settings.microsoft_ad_library_enabled:
            return [failed_item(self.name, "bing", target, "blocked", "connector disabled")]
        kind, value, limit, relevant_only = parse_target(target, self._settings.platform_max_items)
        try:
            ads, cached_at = self._ads(kind, value, limit)
        except AdLibraryError as exc:
            status: FetchStatus = "blocked" if exc.throttled else "error"
            return [failed_item(self.name, "bing", target, status, str(exc))]
        kept = [a for a in ads if not relevant_only or is_relevant(a)]
        dropped = len(ads) - len(kept)
        if dropped:
            log.info("ms ad library %r: %d of %d ads not about investing", value, dropped, len(ads))
        kept = kept[:limit]
        kept = self._with_details(kept)
        prov: dict[str, Any] = {"country_code": self._settings.microsoft_ad_library_country}
        if cached_at:
            prov["cached_at"] = cached_at
        items = [ad_item(ad, target, **prov) for ad in kept]
        return items + self._landing_pages(kept)

    # --- API calls -----------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{API_URL}/{path}"
        max_wait = self._settings.microsoft_ad_library_max_wait_s
        for attempt in range(3):
            left = self._fetcher.cooldown_left(url)
            if 0 < left <= max_wait:
                time.sleep(left + 1.0)  # a short throttle: wait it out rather than fail the run
                left = self._fetcher.cooldown_left(url)
            if left > 0:
                raise AdLibraryError(
                    f"Microsoft Ad Library API throttled us; paused for {left:.0f} s",
                    throttled=True,
                )
            self._fetcher.wait(url, self._settings.microsoft_ad_library_interval_s)
            try:
                with api_client(self._fetcher, self._settings, self._transport) as client:
                    response = client.get(url, params=params)
            except httpx.HTTPError as exc:
                raise AdLibraryError(f"Microsoft Ad Library API {type(exc).__name__}") from None
            if response.status_code != 429:
                break
            pause = retry_after_s(response.headers.get("Retry-After")) or THROTTLE_COOLDOWN_S
            self._fetcher.start_cooldown(url, pause)
            if attempt == 2 or pause > max_wait:
                raise AdLibraryError(
                    "Microsoft Ad Library API HTTP 429 (throttled)", throttled=True
                )
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code >= 400 or not isinstance(data, dict):
            message = ""
            if isinstance(data, dict):
                message = str((data.get("error") or {}).get("message") or "")[:300]
            raise AdLibraryError(f"Microsoft Ad Library API HTTP {response.status_code} {message}")
        return data

    def _cached_get(self, path: str, params: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """A fresh answer (and cache it), or the cached one when the API is empty or throttled.

        Returns the answer and, when it came from the cache, the time it was fetched.
        """
        key = hashlib.sha1(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
        cached = self._cache.get(key)
        try:
            data = self._get(path, params)
        except AdLibraryError:
            if cached is None:
                raise
            entry = json.loads(cached)
            return entry["data"], entry["at"]
        if not data.get("value") and "AdId" not in data and cached is not None:
            entry = json.loads(cached)
            return entry["data"], entry["at"]
        entry = {"at": datetime.now(UTC).isoformat(), "data": data}
        self._cache.set(key, json.dumps(entry), self._settings.microsoft_ad_library_cache_ttl_s)
        return data, None

    def _ads(self, kind: str, value: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"countryCodes": str(self._settings.microsoft_ad_library_country)}
        if kind == "advertiser":
            params["advertiserId"] = value
        else:
            params["searchText"] = value
        ads: list[dict[str, Any]] = []
        cached_at: str | None = None
        # The relevance filter drops some ads: read one page more than `limit` needs.
        for page_no in range(limit // PAGE + 1):
            try:
                data, at = self._cached_get("Ads", {**params, "top": PAGE, "skip": page_no * PAGE})
            except AdLibraryError:
                if ads:  # keep what the first pages gave
                    break
                raise
            cached_at = cached_at or at
            page = [a for a in data.get("value") or [] if isinstance(a, dict)]
            ads += page
            if len(page) < PAGE or (page_no + 1) * PAGE >= int(data.get("@odata.count") or 0):
                break
        return list({str(a.get("AdId")): a for a in ads}.values()), cached_at

    def _with_details(self, ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        budget = self._settings.microsoft_ad_library_details
        result = []
        for ad in ads:
            if budget > 0 and ad.get("AdId"):
                budget -= 1
                try:
                    detail, _ = self._cached_get(f"Ads/{ad['AdId']}", {"expand": DETAILS_EXPAND})
                except AdLibraryError as exc:
                    log.info("ms ad library details for %s: %s", ad.get("AdId"), exc)
                    if exc.throttled:
                        budget = 0
                else:
                    if isinstance(detail.get("AdDetails"), dict):
                        ad = {**ad, "AdDetails": detail["AdDetails"]}
            result.append(ad)
        return result

    # --- landing pages ---------------------------------------------------------------------

    def _landing_pages(self, ads: list[dict[str, Any]]) -> list[CollectedItem]:
        follow = self._settings.microsoft_ad_library_follow
        if follow <= 0:
            return []
        seen: dict[str, dict[str, Any]] = {}
        for ad in ads:
            dest = str(ad.get("DestinationUrl") or "").strip()
            if dest.startswith(("http://", "https://")) and dest not in seen:
                seen[dest] = ad
            if len(seen) >= follow:
                break
        if not seen:
            return []
        if self._web is None:
            # Imported here: the web collector pulls in the browser renderer.
            from investwatch.collectors.web import WebCollector

            self._web = WebCollector(settings=self._settings)
        items: list[CollectedItem] = []
        for dest, ad in seen.items():
            item: CollectedItem = self._web.page(
                dest,
                discovered_by=self.name,
                ad_id=str(ad.get("AdId") or ""),
                advertiser=str(ad.get("AdvertiserName") or ""),
                ad_url=ad_url(str(ad.get("AdId") or "")),
            )
            if item.fetch_status == "ok" and not is_investment_page(item.text):
                # Out of scope (proteins, camera bags, game skins): not monitored material.
                log.info("landing page %s is not about investing; dropped", dest)
                continue
            items.append(item)
        return items
