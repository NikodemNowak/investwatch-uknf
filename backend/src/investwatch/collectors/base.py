"""Collector protocol and the polite HTTP fetcher shared by all collectors.

Compliant by construction (ADR 0008):
- every request names the bot (`InvestWatchBot/<ver> (+contact)`), User-Agents only rotate
  within that identity;
- robots.txt is always obeyed for the `InvestWatchBot` token (no off switch), `Crawl-delay`
  lengthens the per-domain interval;
- social-platform and search-engine hosts are never fetched (official APIs only);
- TDM reservations (art. 26³ pr. aut.: `tdm-reservation` header or meta tag,
  `/.well-known/tdmrep.json`) are honoured;
- a 401/403/429 or a bot challenge puts the domain on cooldown; nothing is retried through
  another proxy or User-Agent. Proxies are only an egress choice.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import itertools
import json
import logging
import random
import re
import socket
import threading
import time
import urllib.robotparser
from collections.abc import Callable, Iterator
from functools import cache
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import redis
import tldextract

from investwatch.collectors.policy import platform_rejection
from investwatch.collectors.schemas import CollectedItem, FetchResult, RobotsDecision
from investwatch.config import BOT_NAME, Settings, get_settings

log = logging.getLogger(__name__)

ROBOTS_TOKEN = BOT_NAME
"""The product token robots.txt rules are matched against."""

# Bundled public-suffix snapshot: no network call at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=())

_TDM_META = re.compile(
    r"<meta[^>]+name=[\"']tdm-reservation[\"'][^>]*content=[\"']\s*1\s*[\"']"
    r"|<meta[^>]+content=[\"']\s*1\s*[\"'][^>]*name=[\"']tdm-reservation[\"']",
    re.I,
)
_CHALLENGE_MARKERS = ("<title>just a moment...</title>", "captcha-delivery.com", "cf-chl-")
"""Bot-challenge pages (Cloudflare, DataDome): a refusal, never something to solve."""
TDM_REASON = "TDM reservation (art. 26³ pr. aut.)"


class Collector(Protocol):
    """A source adapter. `target` meaning depends on the collector (URL, handle, path)."""

    name: str

    def collect(self, target: str) -> list[CollectedItem]:
        """Fetch the target and return what was found (may be empty)."""
        ...


def domain_of(url: str) -> str:
    """Return the registrable domain (e.g. `example.co.uk`), or the host for bare names."""
    host = urlsplit(url).hostname or ""
    parts = _extract(host)
    return parts.top_domain_under_public_suffix or host


class RateLimiter(Protocol):
    """Blocks until a request to `domain` is allowed."""

    def wait(self, domain: str, interval_s: float | None = None) -> None:
        """Sleep as needed; `interval_s` (e.g. `Crawl-delay`) may only lengthen the interval."""
        ...


class MemoryRateLimiter:
    """Per-process limiter."""

    def __init__(self, min_interval_s: float) -> None:
        """Set the minimum interval between requests to one domain."""
        self._interval = min_interval_s
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str, interval_s: float | None = None) -> None:
        """Sleep as needed to respect the per-domain interval."""
        interval = max(self._interval, interval_s or 0.0)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(domain, 0.0))
            self._next[domain] = slot + interval
        if slot > now:
            time.sleep(slot - now)


class RedisRateLimiter:
    """Limiter shared by every worker: one `SET NX PX` token per domain and interval."""

    def __init__(self, client: redis.Redis, min_interval_s: float) -> None:
        """Use `client` for the shared token."""
        self._client = client
        self._ms = max(1, int(min_interval_s * 1000))

    def wait(self, domain: str, interval_s: float | None = None) -> None:
        """Sleep as needed to respect the per-domain interval."""
        key = f"iw:ratelimit:{domain}"
        ms = max(self._ms, int((interval_s or 0.0) * 1000))
        while not self._client.set(key, "1", nx=True, px=ms):
            time.sleep(0.1)


@cache
def get_rate_limiter() -> RateLimiter:
    """Return the limiter for this process (Redis-backed unless running eagerly)."""
    settings = get_settings()
    if settings.celery_eager or settings.realtime_backend == "memory":
        return MemoryRateLimiter(settings.collector_min_interval_s)
    return RedisRateLimiter(
        redis.Redis.from_url(settings.redis_url), settings.collector_min_interval_s
    )


class Cooldown(Protocol):
    """Domains that refused us recently; they are not contacted until the cooldown ends."""

    def remaining(self, domain: str) -> float:
        """Seconds left on `domain`'s cooldown (0 = free)."""
        ...

    def start(self, domain: str, seconds: float) -> None:
        """Put `domain` on cooldown for `seconds`."""
        ...


class MemoryCooldown:
    """Per-process cooldown."""

    def __init__(self) -> None:
        """Start with no domain on cooldown."""
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def remaining(self, domain: str) -> float:
        """Seconds left on `domain`'s cooldown (0 = free)."""
        with self._lock:
            return max(0.0, self._until.get(domain, 0.0) - time.monotonic())

    def start(self, domain: str, seconds: float) -> None:
        """Put `domain` on cooldown for `seconds`."""
        with self._lock:
            self._until[domain] = max(self._until.get(domain, 0.0), time.monotonic() + seconds)


class RedisCooldown:
    """Cooldown shared by every worker (`iw:cooldown:<domain>` with a TTL)."""

    def __init__(self, client: redis.Redis) -> None:
        """Use `client` for the shared keys."""
        self._client = client

    def remaining(self, domain: str) -> float:
        """Seconds left on `domain`'s cooldown (0 = free)."""
        ttl = self._client.pttl(f"iw:cooldown:{domain}")
        return max(0.0, int(ttl) / 1000) if isinstance(ttl, int) else 0.0

    def start(self, domain: str, seconds: float) -> None:
        """Put `domain` on cooldown for `seconds` (never shortens a running one)."""
        key = f"iw:cooldown:{domain}"
        if self.remaining(domain) < seconds:
            self._client.set(key, "1", px=max(1, int(seconds * 1000)))


@cache
def get_cooldown() -> Cooldown:
    """Return the cooldown store for this process (Redis-backed unless running eagerly)."""
    settings = get_settings()
    if settings.celery_eager or settings.realtime_backend == "memory":
        return MemoryCooldown()
    return RedisCooldown(redis.Redis.from_url(settings.redis_url))


def retry_after_s(value: str | None) -> float:
    """`Retry-After` in seconds (delta-seconds form only; dates are ignored)."""
    try:
        return max(0.0, float(value)) if value else 0.0
    except ValueError:
        return 0.0


def tdm_reserved_in_html(html: str) -> bool:
    """True for a `<meta name="tdm-reservation" content="1">` in the page head."""
    return bool(_TDM_META.search(html[:200_000]))


def tdmrep_reserves(body: str, path: str) -> bool:
    """True when a `/.well-known/tdmrep.json` rule matching `path` reserves TDM rights."""
    try:
        rules = json.loads(body)
    except ValueError:
        return False
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            continue
        location = str(rule.get("location") or "")
        if (
            location
            and fnmatch.fnmatchcase(path or "/", location)
            and (str(rule.get("tdm-reservation")) == "1")
        ):
            return True
    return False


UrlGuard = Callable[[str], str | None]
"""Returns why a URL must not be fetched, or None when it is fine."""


class BlockedURLError(httpx.RequestError):
    """A request (typically a redirect hop) was refused by the URL guard."""


def redact_proxy(proxy: str | None) -> str | None:
    """`scheme://host:port` of a proxy URL: credentials never reach the trace or the UI."""
    if not proxy:
        return None
    parts = urlsplit(proxy)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}" if parts.scheme else f"{host}{port}"


def _result(url: str, status: str, error: str, code: int | None = None) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=code,
        html="",
        content_type=None,
        fetch_status=status,
        error=error,
    )


class PoliteFetcher:
    """HTTP GET as InvestWatchBot: robots.txt, TDM, platform deny-list, rate limit, cooldown."""

    def __init__(
        self,
        settings: Settings | None = None,
        limiter: RateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        url_guard: UrlGuard | None = None,
        cooldown: Cooldown | None = None,
    ) -> None:
        """Build a fetcher; `transport` lets tests replace the network.

        `url_guard` is checked before every request, redirect hops included, so a public URL
        cannot bounce the fetcher to an internal address or a platform host.
        """
        self._settings = settings or get_settings()
        self._limiter = limiter or get_rate_limiter()
        self._cooldown = cooldown or get_cooldown()
        self._transport = transport
        self._guard = url_guard
        self._agents = self._settings.user_agents
        proxies: list[str | None] = list(self._settings.proxy_urls) or [None]
        self._proxies: Iterator[str | None] = itertools.cycle(proxies)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._tdmrep: dict[str, str | None] = {}

    def _check(self, request: httpx.Request) -> None:
        url = str(request.url)
        reason = platform_rejection(url) or (self._guard(url) if self._guard else None)
        if reason:
            raise BlockedURLError(f"{request.url}: {reason}", request=request)

    def _client(self, user_agent: str, proxy: str | None = None) -> httpx.Client:
        return httpx.Client(
            transport=self._transport,
            proxy=None if self._transport else proxy,
            timeout=self._settings.collector_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "pl,en;q=0.8"},
            event_hooks={"request": [self._check]},
        )

    def proxy(self) -> str | None:
        """Next egress proxy (for the browser), None for a direct connection."""
        return next(self._proxies)

    def wait(self, url: str, interval_s: float | None = None) -> None:
        """Block until a request to `url`'s domain is allowed (for non-httpx clients).

        `interval_s` may only lengthen the per-domain interval (an API's stricter limit).
        """
        self._limiter.wait(domain_of(url), interval_s)

    def user_agent(self) -> str:
        """Pick a User-Agent from the pool (all of them name InvestWatchBot)."""
        return random.choice(self._agents)

    def cooldown_left(self, url: str) -> float:
        """Seconds until `url`'s domain may be contacted again after a refusal."""
        return self._cooldown.remaining(domain_of(url))

    def start_cooldown(self, url: str, seconds: float | None = None) -> None:
        """Stop contacting `url`'s domain (an API that rate-limited us) for a while."""
        self._cooldown.start(domain_of(url), seconds or self._settings.collector_cooldown_s)

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        """Check robots.txt for `url` as `InvestWatchBot` (cached per origin)."""
        return self.robots_decision(url) != "disallowed"

    def robots_decision(self, url: str) -> RobotsDecision:
        """robots.txt verdict for `url` as `InvestWatchBot`, kept in the fetch trace."""
        parser = self._robots_for(url)
        if parser is None:
            return "missing"
        return "allowed" if parser.can_fetch(ROBOTS_TOKEN, url) else "disallowed"

    def crawl_delay(self, url: str) -> float | None:
        """`Crawl-delay` for InvestWatchBot (or `*`) on `url`'s origin, if any."""
        parser = self._robots_for(url)
        delay = parser.crawl_delay(ROBOTS_TOKEN) if parser is not None else None
        return float(delay) if delay is not None else None

    def sitemaps(self, url: str) -> list[str]:
        """`Sitemap:` lines of `url`'s robots.txt."""
        parser = self._robots_for(url)
        return list(parser.site_maps() or []) if parser is not None else []

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        parser = urllib.robotparser.RobotFileParser(f"{origin}/robots.txt")
        try:
            with self._client(self.user_agent(), self.proxy()) as client:
                response = client.get(f"{origin}/robots.txt")
        except httpx.HTTPError as exc:
            log.warning("robots.txt unreachable for %s (%s); assuming allowed", origin, exc)
            return None
        if response.status_code >= 500:
            parser.parse(["User-agent: *", "Disallow: /"])  # RFC 9309: server error = disallow
        elif response.status_code >= 400:
            return None
        else:
            parser.parse(response.text.splitlines())
        return parser

    def _tdm_reserved_by_origin(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._tdmrep:
            body: str | None = None
            try:
                with self._client(self.user_agent(), self.proxy()) as client:
                    response = client.get(f"{origin}/.well-known/tdmrep.json")
                if response.status_code == 200:
                    body = response.text
            except httpx.HTTPError:
                body = None
            self._tdmrep[origin] = body
        body = self._tdmrep[origin]
        return bool(body) and tdmrep_reserves(body or "", parts.path)

    def fetch(self, url: str) -> FetchResult:
        """GET `url` politely; never raises for HTTP or network errors."""
        reason = platform_rejection(url)
        if reason:
            return _result(url, "blocked", reason)
        domain = domain_of(url)
        left = self._cooldown.remaining(domain)
        if left > 0:
            return _result(url, "blocked", f"domain cooling down after a refusal ({left:.0f} s)")
        robots = self.robots_decision(url)
        if robots == "disallowed":
            return _result(url, "blocked", "disallowed by robots.txt").model_copy(
                update={"robots": robots}
            )
        if self._tdm_reserved_by_origin(url):
            return _result(url, "blocked", f"{TDM_REASON}: tdmrep.json").model_copy(
                update={"robots": robots}
            )
        agent = self.user_agent()
        proxy = None if self._transport else next(self._proxies)
        delay = self.crawl_delay(url)
        trace: dict[str, Any] = {
            "user_agent": agent,
            "proxy": redact_proxy(proxy),
            "robots": robots,
            "crawl_delay_s": delay,
        }
        self._limiter.wait(domain, delay)
        started = time.perf_counter()
        try:
            with self._client(agent, proxy) as client:
                response = client.get(url)
        except BlockedURLError as exc:
            return _result(url, "blocked", str(exc)).model_copy(update=trace)
        except httpx.HTTPError as exc:
            return _result(url, "error", str(exc) or type(exc).__name__).model_copy(update=trace)
        trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        status = response.status_code
        final_url = str(response.url)
        text = response.text if status < 400 else ""
        challenge = any(m in response.text[:20_000].lower() for m in _CHALLENGE_MARKERS)
        if status in {401, 403, 429} or challenge:
            seconds = max(
                self._settings.collector_cooldown_s,
                retry_after_s(response.headers.get("retry-after")),
            )
            self._cooldown.start(domain, seconds)
            log.warning("%s refused us (HTTP %s); cooling down %.0f s", domain, status, seconds)
            error = "bot challenge" if challenge and status < 400 else f"HTTP {status}"
            return _result(
                final_url, "blocked", f"{error}; cooldown {seconds:.0f} s", status
            ).model_copy(update=trace)
        if status < 400 and (
            response.headers.get("tdm-reservation", "").strip() == "1" or tdm_reserved_in_html(text)
        ):
            return _result(final_url, "blocked", TDM_REASON, status).model_copy(update=trace)
        fetch_status = "ok" if status < 400 else "blocked" if status == 451 else "error"
        return FetchResult(
            url=url,
            final_url=final_url,
            status_code=status,
            html=text,
            content_type=response.headers.get("content-type"),
            fetch_status=fetch_status,
            error=None if status < 400 else f"HTTP {status}",
            content=response.content if status < 400 else None,
            **trace,
        )


def url_rejection(url: str, allowed_internal_hosts: list[str]) -> str | None:
    """Return why `url` must not be fetched on a user's request (SSRF guard), or None if fine."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "only absolute http(s) URLs are accepted"
    host = parts.hostname
    if host in allowed_internal_hosts:
        return None
    try:
        infos = socket.getaddrinfo(host, parts.port or 80, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return "host cannot be resolved"
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            return "internal addresses are not allowed"
    return None
