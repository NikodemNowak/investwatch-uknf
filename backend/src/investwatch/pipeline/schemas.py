"""Request/response of the `ai` service (`POST ai:/analyze`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from investwatch.core.schemas import (
    Finding,
    FirmMatch,
    ModuleId,
    Post,
    Probability,
    RenderSnapshot,
)

AnalyzeMode = Literal["llm", "rules", "mock"]
RegisterStatus = Literal["registered", "registered_without_advice", "not_registered"]
"""Is the publisher in the KNF registers (with advisory service A5)? Gate of M3."""


class AnalyzeRequest(BaseModel):
    """Body of `POST /analyze` (mirrors `ai/src/investwatch_ai/analyze.py`; extra fields -> 422)."""

    post: Post
    render: RenderSnapshot | None = None
    firm_matches: list[FirmMatch] = []
    mode: AnalyzeMode | None = None
    thresholds: dict[ModuleId, Probability] | None = None
    """The backend `settings` table is the single source of thresholds."""
    register_status: RegisterStatus | None = None
    """Explicit M3 gate, from `registry.register_status`; None = infer from `firm_matches`."""
    defer_llm: bool = False
    """Mode `llm`: rules only now; findings that need the model come back `queued`."""
    embed: bool = True
    knf_warning: str | None = None
    """Listed entity name when the publisher is on the KNF public warning list: the `ai`
    service names it in the M3 finding without raising the score."""


class LlmUsage(BaseModel):
    """Model, token counts and wall time of one LLM review (`ai` `llm.Usage`)."""

    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    ms: float = 0.0


class AnalyzeResponse(BaseModel):
    """Response of `POST /analyze`."""

    findings: list[Finding]
    embedding: list[float] | None = None
    lang: str | None = None
    timings_ms: dict[str, float] = {}
    chars: int = 0
    tokens: int | None = None
    embed_model: str | None = None
    llm: LlmUsage | None = None
    llm_error: str | None = None


class EmbedResponse(BaseModel):
    """Response of `POST ai:/embed`."""

    model: str
    dim: int
    embeddings: list[list[float]]
    tokens: int | None = None


class AnalysisOutcome(BaseModel):
    """What the pipeline did with one post."""

    post_id: str
    duplicate_of: str | None = None
    finding_ids: list[str] = []
    alerted: list[str] = []
    review_queued: list[str] = []
    """Findings waiting for the model's second opinion (`llm` queue)."""
    analyzer: str
    """`ai` or `mock`."""


class ReviewResult(BaseModel):
    """What the `llm` queue did with one finding."""

    finding_id: str
    state: str
    """`core.schemas.LlmReviewState`, or `skipped` when there was nothing to do."""
    changed_rules: list[str] = []
    """Rules whose status the model changed (e.g. `unknown` -> `fail`)."""
    alerted: bool = False
