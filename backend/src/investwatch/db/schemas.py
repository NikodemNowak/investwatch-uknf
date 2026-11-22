"""Read models returned by the repository (not part of the shared AI contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from investwatch.core.schemas import (
    Finding,
    LlmReviewState,
    ModuleId,
    Platform,
    Post,
    Probability,
    RiskLevel,
    Status,
)
from investwatch.registry.schemas import KnfWarning

SourceStatus = Literal["ok", "blocked", "error", "running"]


class TaskTrace(BaseModel):
    """The Celery task that handled a stage (`jobs.tasks.task_info`)."""

    task: str
    task_id: str | None = None
    queue: str
    worker: str | None = None
    retries: int = 0
    job_id: str | None = None
    """"Check URL" job the task belongs to, if any."""


class LlmTrace(BaseModel):
    """The model's second opinion on a post (`llm` queue)."""

    state: LlmReviewState
    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    ms: float | None = None
    """Wall time of the model call (CPU: tens of seconds)."""
    error: str | None = None
    finished_at: datetime | None = None
    task: TaskTrace | None = None


class ProcessingTrace(BaseModel):
    """What the pipeline did with one post, for the case-file footer and the slides."""

    analyzer: str
    """`ai` or `mock` (the `ai` service was unreachable)."""
    analyzed_at: datetime
    chars: int
    tokens: int | None = None
    embed_model: str | None = None
    embedding_dim: int | None = None
    lang: str | None = None
    rules_version: str | None = None
    timings_ms: dict[str, float] = {}
    """Fast pass in the `ai` service: preprocess, rules, embed, total."""
    llm: LlmTrace | None = None
    task: TaskTrace | None = None
    """The `analyze` task that ran the fast pass (None outside Celery)."""


class Occurrence(BaseModel):
    """One location of the material: the analysed post or a duplicate of it."""

    post_id: UUID
    url: str
    platform: Platform
    author: str
    first_seen_at: datetime
    last_seen_at: datetime


class FindingView(Finding):
    """A finding with its post inlined, as listed by `GET /api/findings`."""

    post: Post
    trace: ProcessingTrace | None = None
    """Processing trace of the post (None for posts never run through the pipeline)."""
    knf_warning: KnfWarning | None = None
    """The publisher is on the KNF public warning list (a flag, not part of the score)."""
    occurrences: list[Occurrence] = Field(default_factory=list)
    """Occurrence group: the analysed post first, then its duplicates (same text and layout)
    by first sighting. `duplicates` is `len(occurrences) - 1`."""
    first_seen_at: datetime | None = None
    """Earliest sighting over the whole group."""
    last_seen_at: datetime | None = None
    """Latest sighting over the whole group."""


class FindingsPage(BaseModel):
    """One page of findings."""

    items: list[FindingView]
    total: int
    page: int
    page_size: int


class FindingFilters(BaseModel):
    """Filters accepted by `GET /api/findings`."""

    model_config = ConfigDict(extra="forbid")

    module: ModuleId | None = None
    platform: list[Platform] = Field(default_factory=list)
    """Any of these platforms (empty: all)."""
    collector: str | None = None
    risk_level: list[RiskLevel] = Field(default_factory=list)
    """Any of these risk levels (empty: all)."""
    status: list[Status] = Field(default_factory=list)
    """Any of these statuses (empty: all); `new` + `in_review` is the open queue."""
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_score: Probability | None = None
    q: str | None = None
    sort: Literal["created_at", "score"] = "created_at"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)

    @field_validator("platform", "risk_level", "status", mode="before")
    @classmethod
    def _one_or_many(cls, value: object) -> object:
        """A single value is a one-element list (`FindingFilters(status="new")`)."""
        if value is None:
            return []
        return [value] if isinstance(value, str) else value


class Thresholds(BaseModel):
    """Alert threshold per module (score >= threshold raises an alert).

    Defaults are the thresholds `make train` chose on the train split
    (`ai/src/investwatch_ai/classifier/weights/thresholds.json`, the ones `make eval` reports),
    so what the screen alerts on is what was evaluated; a test keeps them equal. The
    `settings` table holds the analyst's changes ("Czułość") and the values are sent to the
    `ai` service with every `/analyze` request.
    """

    m1_third_party_ad: Probability = 0.2
    m2_risk_disclosure: Probability = 0.3
    m3_shadow_advisory: Probability = 0.12

    def for_module(self, module: ModuleId) -> float:
        """Return the threshold of one module."""
        value: float = getattr(self, module)
        return value

    def as_dict(self) -> dict[ModuleId, float]:
        """Return `{module: threshold}`."""
        return {
            "m1_third_party_ad": self.m1_third_party_ad,
            "m2_risk_disclosure": self.m2_risk_disclosure,
            "m3_shadow_advisory": self.m3_shadow_advisory,
        }


class ModuleSummary(BaseModel):
    """Counts for one module."""

    module: ModuleId
    total: int
    high: int
    medium: int
    low: int
    new: int


class Summary(BaseModel):
    """Response of `GET /api/stats/summary`."""

    posts: int
    findings: int
    open_findings: int
    """Status `new` or `in_review`."""
    modules: list[ModuleSummary]
    last_finding_at: datetime | None


RunStatusView = Literal["ok", "partial", "error", "running"]


class Source(BaseModel):
    """A monitored source (`frontend/src/api/types.ts` `Source` plus scheduler fields)."""

    id: UUID
    name: str
    platform: Platform
    collector: str
    target: str
    url: str
    """Same as `target`; the name the dashboard uses."""
    module_hint: ModuleId | None
    cron: str
    schedule: str
    """Same as `cron`; the name the dashboard uses."""
    enabled: bool
    next_run_at: datetime | None
    last_status: SourceStatus | None
    last_run_at: datetime | None
    last_run_status: RunStatusView | None
    """`blocked` is reported as `error` here; `last_status` keeps the precise value."""
    last_run_items: int
    created_at: datetime
    access_mode: str | None = None
    """How the collector reaches its source (`official_api`, `crawler`, `file_import`, ...)."""
    connector_status: str | None = None
    """`ready`, `needs_credentials` ("wymaga klucza"), `needs_approval` ("wymaga zgody
    platformy") or `disabled`; filled by the API from the current settings."""
    connector_reason: str | None = None
    """Why a `disabled` source never runs (Polish), e.g. its collector was removed."""


class ScrapeRun(BaseModel):
    """One execution of a source."""

    id: UUID
    source_id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: SourceStatus
    items_new: int
    items_seen: int
    error: str | None


class UpsertResult(BaseModel):
    """Outcome of storing a collected post."""

    post: Post
    created: bool
    changed: bool
    """True when new, or when the text changed since the last visit (re-analysis needed)."""
