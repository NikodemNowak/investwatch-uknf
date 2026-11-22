"""Small TTL cache for discovery answers (Redis shared by workers, or per process)."""

from __future__ import annotations

import time
from functools import cache
from typing import Protocol

import redis

from investwatch.config import get_settings


class TextCache(Protocol):
    """`get`/`set` of short text values with a TTL."""

    def get(self, key: str) -> str | None:
        """Cached value or None."""
        ...

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store `value` for `ttl_s` seconds."""
        ...


class MemoryCache:
    """Per-process cache."""

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        """Cached value or None."""
        hit = self._data.get(key)
        return hit[1] if hit and hit[0] > time.monotonic() else None

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store `value` for `ttl_s` seconds."""
        self._data[key] = (time.monotonic() + ttl_s, value)


class RedisCache:
    """Cache shared by every worker."""

    def __init__(self, client: redis.Redis) -> None:
        """Use `client`."""
        self._client = client

    def get(self, key: str) -> str | None:
        """Cached value or None."""
        value = self._client.get(key)
        return value.decode() if isinstance(value, bytes) else None

    def set(self, key: str, value: str, ttl_s: int) -> None:
        """Store `value` for `ttl_s` seconds."""
        self._client.set(key, value, ex=max(1, ttl_s))


@cache
def get_cache() -> TextCache:
    """Return the discovery cache for this process."""
    settings = get_settings()
    if settings.celery_eager or settings.realtime_backend == "memory":
        return MemoryCache()
    return RedisCache(redis.Redis.from_url(settings.redis_url))
