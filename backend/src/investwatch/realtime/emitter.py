"""Emit Socket.IO events from any process (API, Celery workers) through Redis."""

from __future__ import annotations

import logging
from functools import cache
from typing import Any, Protocol

import redis
import socketio

from investwatch.config import get_settings
from investwatch.core.schemas import Alert, Finding
from investwatch.realtime.schemas import JobEvent

log = logging.getLogger(__name__)

ALERT_EVENT = "alert"
JOB_EVENT = "job"
FINDING_UPDATED_EVENT = "finding_updated"
JOB_TTL_S = 24 * 3600


class Emitter(Protocol):
    """Fire-and-forget event publisher."""

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Broadcast `event` with a JSON payload to all connected clients."""
        ...

    def save_job(self, event: JobEvent) -> None:
        """Remember the latest state of a job (for `GET /api/check/{job_id}`)."""
        ...

    def load_job(self, job_id: str) -> JobEvent | None:
        """Return the latest state of a job."""
        ...


class RedisEmitter:
    """Write-only Socket.IO manager: the API process relays the events to its clients."""

    def __init__(self, redis_url: str) -> None:
        """Create the manager (connects lazily)."""
        self._manager = socketio.RedisManager(redis_url, write_only=True)
        self._redis = redis.Redis.from_url(redis_url)

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Broadcast `event` with a JSON payload to all connected clients."""
        self._manager.emit(event, data, namespace="/")

    def save_job(self, event: JobEvent) -> None:
        """Remember the latest state of a job for a day."""
        self._redis.set(f"iw:job:{event.job_id}", event.model_dump_json(), ex=JOB_TTL_S)

    def load_job(self, job_id: str) -> JobEvent | None:
        """Return the latest state of a job."""
        raw = self._redis.get(f"iw:job:{job_id}")
        return JobEvent.model_validate_json(raw) if raw else None


class MemoryEmitter:
    """Records events in memory (tests, single-process dev)."""

    def __init__(self) -> None:
        """Start with no events."""
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.jobs: dict[str, JobEvent] = {}

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Record the event."""
        self.events.append((event, data))

    def save_job(self, event: JobEvent) -> None:
        """Remember the latest state of a job."""
        self.jobs[event.job_id] = event

    def load_job(self, job_id: str) -> JobEvent | None:
        """Return the latest state of a job."""
        return self.jobs.get(job_id)


@cache
def get_emitter() -> Emitter:
    """Return the configured emitter."""
    settings = get_settings()
    if settings.realtime_backend == "memory":
        return MemoryEmitter()
    return RedisEmitter(settings.redis_url)


def _safe_emit(event: str, data: dict[str, Any]) -> None:
    try:
        get_emitter().emit(event, data)
    except Exception:
        # A dead Redis must not fail the analysis; the finding is already stored.
        log.exception("failed to emit %s", event)


def emit_alert(alert: Alert) -> None:
    """Broadcast an `alert` event."""
    _safe_emit(ALERT_EVENT, alert.model_dump(mode="json"))


def emit_finding_updated(finding: Finding) -> None:
    """Broadcast `finding_updated` (the model's second opinion arrived) with the full record."""
    _safe_emit(FINDING_UPDATED_EVENT, finding.model_dump(mode="json"))


def emit_job(event: JobEvent) -> None:
    """Record and broadcast a `job` progress event."""
    try:
        get_emitter().save_job(event)
    except Exception:
        log.exception("failed to save job %s", event.job_id)
    _safe_emit(JOB_EVENT, event.model_dump(mode="json"))


def load_job(job_id: str) -> JobEvent | None:
    """Return the latest recorded state of a job."""
    return get_emitter().load_job(job_id)
