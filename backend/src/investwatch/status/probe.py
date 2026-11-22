"""Probe each service with a short timeout, in parallel; results are cached for a few seconds."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import httpx
import redis
from sqlalchemy import text

from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.session import session_scope
from investwatch.status.schemas import (
    AiInfo,
    NextRun,
    QueueStatus,
    ServiceName,
    ServiceState,
    ServiceStatus,
    SystemStatus,
)
from investwatch.storage.minio import MinioStore, get_store

log = logging.getLogger(__name__)

VERSION = "0.1.0"
TIMEOUT_S = 1.5
INSPECT_TIMEOUT_S = 1.0
"""`celery inspect` always waits the full timeout for replies, so keep it short."""
CACHE_S = 10.0
BEAT_TICK_KEY = "investwatch:beat:last_tick"
"""Set by `tick_sources` on every Beat tick (each minute)."""
BEAT_STALE_S = 180.0

Probe = tuple[ServiceState, str | None]


def mark_beat_tick(now: datetime | None = None) -> None:
    """Record a Beat tick in Redis so the API (another container) can tell Beat is alive."""
    settings = get_settings()
    if settings.celery_eager:
        return
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_timeout=TIMEOUT_S)
        client.set(BEAT_TICK_KEY, (now or datetime.now(UTC)).isoformat(), ex=3600)
    except redis.RedisError:
        log.warning("cannot record the beat tick", exc_info=True)


def _database() -> Probe:
    with session_scope() as session:
        session.execute(text("SELECT 1"))
        return "ok", session.get_bind().dialect.name


def _redis() -> tuple[Probe, datetime | None]:
    client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=TIMEOUT_S)
    client.ping()
    raw = client.get(BEAT_TICK_KEY)
    tick = datetime.fromisoformat(raw.decode()) if isinstance(raw, bytes) else None
    return ("ok", None), tick


def _minio() -> Probe:
    store = get_store()
    if not isinstance(store, MinioStore):
        return "ok", "memory"
    return ("ok", get_settings().minio_bucket) if store.ping() else ("down", "bucket missing")


def _workers() -> tuple[Probe, list[QueueStatus]]:
    if get_settings().celery_eager:
        return ("disabled", "eager"), []
    from investwatch.jobs.celery_app import celery_app

    replies: dict[str, Any] = (
        celery_app.control.inspect(timeout=INSPECT_TIMEOUT_S).active_queues() or {}
    )
    by_queue: dict[str, list[str]] = {}
    for worker, queues in replies.items():
        for queue in queues or []:
            by_queue.setdefault(str(queue.get("name")), []).append(worker.split("@")[-1])
    queues = [QueueStatus(name=q, workers=sorted(w)) for q, w in sorted(by_queue.items())]
    expected = {"check", "scrape", "analyze", "maintenance"}
    if get_settings().ai_mode == "llm":  # the lite stack (AI_MODE=rules) runs no worker-llm
        expected |= {"llm_priority", "llm"}
    missing = sorted(expected - set(by_queue))
    if not replies:
        return ("down", "no worker answered"), queues
    if missing:
        return ("degraded", "no consumer: " + ", ".join(missing)), queues
    return ("ok", f"{len(replies)}"), queues


def _ai() -> tuple[Probe, Probe, AiInfo | None]:
    settings = get_settings()
    if settings.ai_mode == "mock":
        return ("disabled", "mock"), ("disabled", None), AiInfo(mode="mock")
    body = httpx.get(f"{settings.ai_url}/health", timeout=TIMEOUT_S).json()
    info = AiInfo.model_validate(body)
    ollama = str(body.get("ollama", "down"))
    if ollama == "disabled":
        ollama_probe: Probe = ("disabled", None)
    elif ollama != "up":
        ollama_probe = ("down", None)
    elif info.embed_ready and (info.llm_ready or settings.ai_mode != "llm"):
        ollama_probe = ("ok", info.llm_model)
    else:
        ollama_probe = ("degraded", "pulling models")
    return ("ok", info.rules_version), ollama_probe, info


def _next_run() -> NextRun | None:
    with session_scope() as session:
        due = [s for s in repo.list_sources(session) if s.enabled and s.next_run_at]
    if not due:
        return None
    first = min(due, key=lambda s: s.next_run_at or datetime.max.replace(tzinfo=UTC))
    assert first.next_run_at is not None
    return NextRun(
        source_id=str(first.id), source_name=first.name, cron=first.cron, at=first.next_run_at
    )


def _timed(fn: Callable[[], Any]) -> tuple[Any, float, Exception | None]:
    started = time.perf_counter()
    try:
        out = fn()
    except Exception as exc:
        return None, (time.perf_counter() - started) * 1000, exc
    return out, (time.perf_counter() - started) * 1000, None


def _service(
    name: ServiceName, probe: Probe | None, ms: float, error: Exception | None
) -> ServiceStatus:
    if error is not None or probe is None:
        detail = f"{type(error).__name__}: {error}"[:200] if error else None
        return ServiceStatus(name=name, state="down", detail=detail, latency_ms=round(ms, 1))
    state, detail = probe
    return ServiceStatus(name=name, state=state, detail=detail, latency_ms=round(ms, 1))


def probe_system() -> SystemStatus:
    """Probe every service now (about `TIMEOUT_S` at worst: the probes run in parallel)."""
    jobs: dict[str, Callable[[], Any]] = {
        "database": _database,
        "redis": _redis,
        "minio": _minio,
        "workers": _workers,
        "ai": _ai,
        "next_run": _next_run,
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(_timed, fn) for name, fn in jobs.items()}
        results = {name: f.result() for name, f in futures.items()}

    services = [ServiceStatus(name="api", state="ok", detail=VERSION, latency_ms=0.0)]
    services.append(_service("database", *results["database"]))
    redis_out, redis_ms, redis_err = results["redis"]
    services.append(_service("redis", redis_out[0] if redis_out else None, redis_ms, redis_err))
    tick: datetime | None = redis_out[1] if redis_out else None
    services.append(_service("minio", *results["minio"]))
    workers_out, workers_ms, workers_err = results["workers"]
    services.append(
        _service("workers", workers_out[0] if workers_out else None, workers_ms, workers_err)
    )
    queues: list[QueueStatus] = workers_out[1] if workers_out else []

    if get_settings().celery_eager:
        beat: ServiceStatus = ServiceStatus(name="beat", state="disabled", detail="eager")
    elif tick is None:
        beat = ServiceStatus(name="beat", state="down", detail="no tick recorded")
    else:
        age = (datetime.now(UTC) - tick).total_seconds()
        beat = ServiceStatus(
            name="beat",
            state="ok" if age < BEAT_STALE_S else "down",
            detail=f"last tick {age:.0f} s ago",
        )
    services.append(beat)

    ai_out, ai_ms, ai_err = results["ai"]
    services.append(_service("ai", ai_out[0] if ai_out else None, ai_ms, ai_err))
    services.append(
        _service("ollama", ai_out[1] if ai_out else None, ai_ms, ai_err)
        if ai_out or ai_err is None
        else ServiceStatus(name="ollama", state="down", detail="ai service unreachable")
    )
    next_out, _, next_err = results["next_run"]
    if next_err is not None:
        log.warning("cannot read the next run: %s", next_err)
    return SystemStatus(
        checked_at=datetime.now(UTC),
        version=VERSION,
        services=services,
        queues=queues,
        next_run=next_out,
        beat_last_tick=tick,
        ai=ai_out[2] if ai_out else None,
    )


_lock = threading.Lock()
_cached: tuple[float, SystemStatus] | None = None


def system_status() -> SystemStatus:
    """`probe_system`, cached for `CACHE_S` so a polling page does not flood the workers."""
    global _cached
    with _lock:
        if _cached is not None and time.monotonic() - _cached[0] < CACHE_S:
            return _cached[1]
    status = probe_system()
    with _lock:
        _cached = (time.monotonic(), status)
    return status


def clear_cache() -> None:
    """Forget the cached status (tests)."""
    global _cached
    with _lock:
        _cached = None
