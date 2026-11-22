"""Response of `GET /api/system`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ServiceName = Literal["api", "database", "redis", "minio", "workers", "beat", "ai", "ollama"]
ServiceState = Literal["ok", "degraded", "down", "disabled"]


class ServiceStatus(BaseModel):
    """One service as probed from the API."""

    name: ServiceName
    state: ServiceState
    detail: str | None = None
    """Technical detail: model names, worker count, error (not translated)."""
    latency_ms: float | None = None


class QueueStatus(BaseModel):
    """A Celery queue and the workers consuming it."""

    name: str
    workers: list[str]


class NextRun(BaseModel):
    """The next source Beat will queue."""

    source_id: str
    source_name: str
    cron: str
    at: datetime


class AiInfo(BaseModel):
    """What the `ai` service runs (from its `/health`)."""

    mode: str
    rules_version: str | None = None
    llm_model: str | None = None
    embed_model: str | None = None
    llm_ready: bool = False
    embed_ready: bool = False


class SystemStatus(BaseModel):
    """Health of every part of the stack, for the status line on Monitoring."""

    checked_at: datetime
    version: str
    services: list[ServiceStatus]
    queues: list[QueueStatus]
    next_run: NextRun | None = None
    beat_last_tick: datetime | None = None
    ai: AiInfo | None = None
