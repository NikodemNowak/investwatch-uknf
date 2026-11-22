"""Polite HTTP for the public-data loaders: honest User-Agent, robots.txt, per-host interval.

The golden-set loaders run by hand (not in the service), so they use their own small client
instead of the collectors' `PoliteFetcher`: one fixed, self-identifying User-Agent, robots.txt
always honoured (no switch) and a fixed minimum interval per host.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "InvestWatchBot/0.1 (+https://github.com/NikodemNowak/investwatch-uknf; "
    "golden-set research, HackNation 2026)"
)
"""Self-identifying UA; robots.txt is evaluated for the `InvestWatchBot` token."""
ROBOTS_TOKEN = "InvestWatchBot"


class RobotsDisallowedError(Exception):
    """robots.txt of the host forbids the URL for our User-Agent."""


class PoliteClient:
    """GET with robots.txt, a minimum per-host interval and an honest User-Agent."""

    def __init__(self, min_interval_s: float = 2.0, timeout_s: float = 30.0) -> None:
        """`min_interval_s` applies per host, robots.txt fetches included."""
        self._interval = min_interval_s
        self._next: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.5"},
            timeout=timeout_s,
            follow_redirects=True,
        )

    def _wait(self, host: str) -> None:
        now = time.monotonic()
        slot = max(now, self._next.get(host, 0.0))
        self._next[host] = slot + self._interval
        if slot > now:
            time.sleep(slot - now)

    def _load_robots(self, origin: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        self._wait(host)
        try:
            resp = self._client.get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            return None  # unreachable host: nothing to fetch anyway
        if resp.status_code in (401, 403):
            return None  # robots.txt itself is denied: treat the site as off-limits
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        return parser

    def allowed(self, url: str) -> bool:
        """Is `url` allowed for us by its host's robots.txt (missing robots.txt = allowed)?"""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin, parts.netloc)
        parser = self._robots[origin]
        return parser is not None and parser.can_fetch(ROBOTS_TOKEN, url)

    def get(self, url: str, *, check_robots: bool = True) -> httpx.Response:
        """Fetch `url`; raise `RobotsDisallowedError` when robots.txt forbids it."""
        if check_robots and not self.allowed(url):
            raise RobotsDisallowedError(url)
        self._wait(urlsplit(url).netloc)
        log.debug("GET %s", url)
        return self._client.get(url)

    def close(self) -> None:
        """Close the connection pool."""
        self._client.close()
