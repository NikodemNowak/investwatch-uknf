"""The `youtube` collector: YouTube Data API v3 (`YOUTUBE_API_KEY`), nothing else.

Targets:
- `search:<N>:<query>` (also the legacy `ytsearchN:<query>`, `N:<query>` or a bare query):
  `search.list` (100 units) restricted to Poland and Polish, then one `videos.list` (1 unit);
- a video URL or 11-character id: `videos.list`;
- `ids:<id>,<id>,...`: known video ids in one `videos.list` call (1 unit per 50 ids);
- a channel URL (`/@handle` or `/channel/UC...`): `channels.list` -> uploads playlist ->
  `playlistItems.list` -> `videos.list` (3 units).

Text for the rules: title + description + tags. Captions are not available with an API key
(they need the video owner's OAuth consent), so there are none. Quota is counted per Pacific
day (Google's reset) and stops at `YOUTUBE_DAILY_UNITS`. The key travels only in the request
query; it is never logged and never stored in `raw`. API policy: stored data is refreshed or
deleted within 30 days (`refresh` + the weekly `refresh_youtube` task).
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import UTC, datetime, timedelta, timezone
from functools import cache
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import redis

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
from investwatch.core.schemas import FetchStatus

log = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/youtube/v3"
TERMS_URL = "https://www.youtube.com/t/terms"
COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}
"""Quota units per call (developers.google.com/youtube/v3/determine_quota_cost)."""
BATCH = 50
"""`videos.list` accepts at most 50 ids per call."""

_LEGACY_SEARCH = re.compile(r"^ytsearch(\d*):(.+)$", re.S)
_NEW_SEARCH = re.compile(r"^search:(?:(\d{1,3}):)?(.+)$", re.S)
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class QuotaCounter(Protocol):
    """Units spent today; `spend` refuses a call that would pass the limit."""

    def spend(self, units: int, limit: int) -> bool:
        """Add `units` and return True, or return False (nothing added) when over `limit`."""
        ...


def quota_day(now: datetime | None = None) -> str:
    """The quota day (YouTube resets at midnight Pacific time)."""
    try:
        tz: Any = ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        tz = timezone(timedelta(hours=-8))
    return (now or datetime.now(UTC)).astimezone(tz).date().isoformat()


class MemoryQuota:
    """Per-process counter (tests, eager mode)."""

    def __init__(self) -> None:
        """Start at zero."""
        self._used: dict[str, int] = {}
        self._lock = threading.Lock()

    def spend(self, units: int, limit: int) -> bool:
        """Add `units` unless that passes `limit`."""
        day = quota_day()
        with self._lock:
            if self._used.get(day, 0) + units > limit:
                return False
            self._used[day] = self._used.get(day, 0) + units
            return True


class RedisQuota:
    """Counter shared by every worker: `iw:quota:youtube:<Pacific date>`."""

    def __init__(self, client: redis.Redis) -> None:
        """Use `client` for the counter."""
        self._client = client

    def spend(self, units: int, limit: int) -> bool:
        """Add `units` unless that passes `limit` (rolled back when it does)."""
        key = f"iw:quota:youtube:{quota_day()}"
        used = int(self._client.incrby(key, units))
        self._client.expire(key, 2 * 24 * 3600)
        if used > limit:
            self._client.decrby(key, units)
            return False
        return True


@cache
def get_quota() -> QuotaCounter:
    """Return the quota counter for this process."""
    settings = get_settings()
    if settings.celery_eager or settings.realtime_backend == "memory":
        return MemoryQuota()
    return RedisQuota(redis.Redis.from_url(settings.redis_url))


class YouTubeApiError(RuntimeError):
    """An API call failed; `status` says whether it is a refusal (`blocked`) or an error."""

    def __init__(self, status: FetchStatus, message: str) -> None:
        """Keep the fetch status next to the message."""
        super().__init__(message)
        self.status: FetchStatus = status


def video_id(target: str) -> str | None:
    """The video id of a watch / shorts / live / youtu.be URL, or of a bare id."""
    value = target.strip()
    if _VIDEO_ID.match(value):
        return value
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if host.endswith("youtu.be"):
        vid = parts.path.strip("/").split("/")[0]
        return vid if _VIDEO_ID.match(vid) else None
    if not host.endswith("youtube.com"):
        return None
    if parts.path == "/watch":
        vid = (parse_qs(parts.query).get("v") or [""])[0]
        return vid if _VIDEO_ID.match(vid) else None
    for prefix in ("/shorts/", "/live/", "/embed/"):
        if parts.path.startswith(prefix):
            vid = parts.path[len(prefix) :].split("/")[0]
            return vid if _VIDEO_ID.match(vid) else None
    return None


def parse_target(target: str, default: int) -> tuple[str, str, int]:
    """Return (kind, value, limit); kind is `search`, `video`, `ids`, `handle` or `channel`."""
    value = target.strip()
    if value.lower().startswith("ids:"):
        ids = [i.strip() for i in value[4:].split(",") if _VIDEO_ID.match(i.strip())]
        if not ids:
            raise ValueError(f"no valid video ids in {value!r}")
        return "ids", ",".join(dict.fromkeys(ids)), len(ids)
    for pattern in (_NEW_SEARCH, _LEGACY_SEARCH):
        match = pattern.match(value)
        if match:
            limit = int(match.group(1)) if match.group(1) else default
            return "search", match.group(2).strip(), max(1, limit)
    vid = video_id(value)
    if vid:
        return "video", vid, 1
    if value.lower().startswith(("http://", "https://")):
        path = urlsplit(value).path.strip("/").split("/")
        if path and path[0].startswith("@"):
            return "handle", path[0], default
        if len(path) >= 2 and path[0] == "channel":
            return "channel", path[1], default
        raise ValueError(f"unsupported YouTube URL: {value}")
    limit, query = split_limit(value, default)
    return "search", query, limit


def video_item(video: dict[str, Any], target: str, **provenance: Any) -> CollectedItem:
    """Map a `videos.list` resource to a collected item."""
    vid = str(video.get("id") or "")
    snippet = video.get("snippet") or {}
    url = f"https://www.youtube.com/watch?v={vid}"
    description = str(snippet.get("description") or "")
    tags = [str(t) for t in snippet.get("tags") or []]
    links = extract_links(description)
    text = join_text(
        str(snippet.get("title") or ""),
        description,
        "Tagi: " + ", ".join(tags) if tags else None,
    )
    channel_id = str(snippet.get("channelId") or "")
    published = snippet.get("publishedAt")
    try:
        published_at = (
            datetime.fromisoformat(str(published).replace("Z", "+00:00")) if published else None
        )
    except ValueError:
        published_at = None
    lang = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
    return CollectedItem(
        platform="youtube",
        collector="youtube",
        external_id=vid,
        url=url,
        author=str(snippet.get("channelTitle") or channel_id or "?"),
        author_url=f"https://www.youtube.com/channel/{channel_id}" if channel_id else None,
        text=text,
        lang=str(lang).split("-")[0] if lang else None,
        published_at=published_at,
        fetch_status="ok" if text else "no_text",
        raw=envelope(
            "youtube",
            url,
            target,
            video,
            links=links,
            candidate_domains=candidate_domains(links),
            terms_url=TERMS_URL,
            retention="refresh or delete within 30 days (YouTube API policy)",
            **provenance,
        ),
    )


class YouTubeApiCollector:
    """YouTube videos through the official Data API v3."""

    name = "youtube"

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        *,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        quota: QuotaCounter | None = None,
    ) -> None:
        """Tests inject the HTTP transport and the quota counter."""
        self._settings = settings or get_settings()
        self._fetcher = fetcher or PoliteFetcher(self._settings)
        self._transport = transport
        self._quota = quota or get_quota()

    def collect(self, target: str) -> list[CollectedItem]:
        """Videos for `target`; never raises (failures become one blocked/error item)."""
        if not self._settings.youtube_api_key:
            return [
                failed_item(
                    self.name,
                    "youtube",
                    target,
                    "blocked",
                    "wymaga klucza: set YOUTUBE_API_KEY (YouTube Data API v3)",
                )
            ]
        try:
            kind, value, limit = parse_target(target, self._settings.platform_max_items)
            if kind == "search":
                ids = self._search(value, limit)
            elif kind == "video":
                ids = [value]
            elif kind == "ids":
                ids = value.split(",")
            else:
                ids = self._uploads(kind, value, limit)
            if not ids:
                return []
            videos = self._videos(ids)
        except YouTubeApiError as exc:
            return [failed_item(self.name, "youtube", target, exc.status, str(exc))]
        except ValueError as exc:
            return [failed_item(self.name, "youtube", target, "error", str(exc))]
        return [video_item(v, target) for v in videos]

    def refresh(self, ids: list[str]) -> tuple[list[CollectedItem], list[str]]:
        """Re-read stored videos: (current items, ids that are gone and must be deleted)."""
        videos = self._videos(ids)
        found = {str(v.get("id")) for v in videos}
        items = [video_item(v, f"refresh:{v.get('id')}") for v in videos]
        return items, [i for i in ids if i not in found]

    # --- API calls -----------------------------------------------------------------------

    def _call(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        units = COST[resource]
        url = f"{API_URL}/{resource}"
        if self._fetcher.cooldown_left(url) > 0:
            raise YouTubeApiError("blocked", "YouTube API cooling down after a refusal")
        if not self._quota.spend(units, self._settings.youtube_daily_units):
            raise YouTubeApiError(
                "blocked",
                f"daily YouTube quota reached ({self._settings.youtube_daily_units} units); "
                "resumes after midnight Pacific time",
            )
        self._fetcher.wait(url)
        query = {**params, "key": self._settings.youtube_api_key}
        try:
            with api_client(self._fetcher, self._settings, self._transport) as client:
                response = client.get(url, params=query)
        except httpx.HTTPError as exc:
            # The request URL carries the key: report only the error type.
            raise YouTubeApiError("error", f"YouTube API {type(exc).__name__}") from None
        if response.status_code >= 400:
            raise self._error(response, url)
        data: dict[str, Any] = response.json()
        return data

    def _error(self, response: httpx.Response, url: str) -> YouTubeApiError:
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        reasons = {str(e.get("reason")) for e in error.get("errors") or [] if isinstance(e, dict)}
        message = str(error.get("message") or "")[:300]
        if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
            self._fetcher.start_cooldown(url)
            return YouTubeApiError("blocked", f"YouTube quota exceeded: {message}")
        if reasons & {"keyInvalid", "keyExpired"} or (
            response.status_code == 400 and "key" in (message.lower())
        ):
            return YouTubeApiError("blocked", "YOUTUBE_API_KEY rejected (invalid or expired)")
        status: FetchStatus = "blocked" if response.status_code in {401, 403, 429} else "error"
        if response.status_code == 429:
            self._fetcher.start_cooldown(url)
        return YouTubeApiError(status, f"YouTube API HTTP {response.status_code}: {message}")

    def _search(self, query: str, limit: int) -> list[str]:
        data = self._call(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "q": query,
                "regionCode": "PL",
                "relevanceLanguage": "pl",
                "maxResults": min(limit, BATCH),
            },
        )
        ids = [
            str((entry.get("id") or {}).get("videoId") or "") for entry in data.get("items") or []
        ]
        return [i for i in ids if i][:limit]

    def _uploads(self, kind: str, value: str, limit: int) -> list[str]:
        params = {"part": "contentDetails", "forHandle" if kind == "handle" else "id": value}
        channels = self._call("channels", params).get("items") or []
        if not channels:
            raise YouTubeApiError("error", f"channel not found: {value}")
        playlist = ((channels[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get(
            "uploads"
        )
        if not playlist:
            return []
        items = (
            self._call(
                "playlistItems",
                {"part": "contentDetails", "playlistId": playlist, "maxResults": min(limit, BATCH)},
            ).get("items")
            or []
        )
        ids = [str((i.get("contentDetails") or {}).get("videoId") or "") for i in items]
        return [i for i in ids if i][:limit]

    def _videos(self, ids: list[str]) -> list[dict[str, Any]]:
        videos: list[dict[str, Any]] = []
        for start in range(0, len(ids), BATCH):
            chunk = ids[start : start + BATCH]
            data = self._call(
                "videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(chunk)}
            )
            videos += [v for v in data.get("items") or [] if isinstance(v, dict)]
        return videos
