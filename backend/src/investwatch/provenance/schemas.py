"""Read model of `GET /api/findings/{id}/trace`."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from investwatch.db.schemas import ProcessingTrace

ObjectKind = Literal["html", "raw", "render", "screenshot"]


class StoredObject(BaseModel):
    """One evidence copy in object storage, with its SHA-256 as stored."""

    kind: ObjectKind
    label: str
    """Viewport for screenshots, otherwise the kind."""
    key: str
    bucket: str
    content_type: str
    bytes: int | None = None
    sha256: str | None = None
    """None when the object is missing (e.g. storage was reset)."""


class SourceInfo(BaseModel):
    """The monitored source (and its schedule) that found the material."""

    id: UUID
    name: str
    collector: str
    cron: str
    next_run_at: datetime | None
    last_run_at: datetime | None


class CollectJob(BaseModel):
    """The Celery task that collected the material (`raw.job`)."""

    task: str
    task_id: str | None = None
    queue: str
    worker: str | None = None
    run_id: str | None = None
    job_id: str | None = None
    """"Check URL" job id, for materials checked by hand."""
    cron: str | None = None


class FetchInfo(BaseModel):
    """How the material was obtained (`raw` envelope written by the collector)."""

    collector: str | None = None
    collector_version: str | None = None
    access_mode: str | None = None
    legal_basis: str | None = None
    source_url: str | None = None
    target: str | None = None
    fetched_at: datetime | None = None
    user_agent: str | None = None
    proxy: str | None = None
    """`scheme://host:port`; None = direct connection."""
    robots: str | None = None
    """`allowed`, `disallowed` or `missing` (no robots.txt); None = not a crawler fetch."""
    crawl_delay_s: float | None = None
    http_status: int | None = None
    elapsed_ms: float | None = None
    render: str | None = None
    """`ok`, `error: ...` or None (rendering disabled / not HTML)."""
    render_ms: float | None = None
    discovered_by: dict[str, Any] | None = None


class ModelParts(BaseModel):
    """`Finding.model` split into its parts, e.g. `gemma+rules-v2+lr-v1-embedding`."""

    rules_version: str | None = None
    llm_model: str | None = None
    classifier: str | None = None
    """Head version, e.g. `lr-v1`."""
    classifier_variant: str | None = None
    """`embedding` (bge-m3 + lexicon) or `lexicon`."""
    mock: bool = False


class SimilarPost(BaseModel):
    """A nearby material by embedding (pgvector cosine)."""

    post_id: UUID
    url: str
    author: str
    similarity: float
    finding_id: UUID | None = None


class UnderTheHood(BaseModel):
    """Everything the "Pod maską" panel shows about one finding."""

    finding_id: UUID
    post_id: UUID
    content_hash: str
    """SHA-256 of the normalised text (dedup key)."""
    render_hash: str | None = None
    tokens: int | None = None
    source: SourceInfo | None = None
    collect_job: CollectJob | None = None
    fetch: FetchInfo | None = None
    objects: list[StoredObject] = []
    trace: ProcessingTrace | None = None
    model: ModelParts
    classifier_note: str | None = None
    """The classifier's sentence from the explanation (probability, logit contributions)."""
    similar: list[SimilarPost] = []
    similar_available: bool = False
    """False off Postgres or without an embedding (nothing to compare)."""
