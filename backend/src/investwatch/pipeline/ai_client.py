"""Client of the `ai` service with a deterministic fallback."""

from __future__ import annotations

import logging

import httpx

from investwatch.config import Settings, get_settings
from investwatch.core.schemas import FirmMatch, ModuleId, Post, RenderSnapshot
from investwatch.pipeline.mock_ai import mock_analyze
from investwatch.pipeline.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EmbedResponse,
    RegisterStatus,
)

log = logging.getLogger(__name__)


def analyze(
    post: Post,
    render: RenderSnapshot | None,
    firm_matches: list[FirmMatch],
    thresholds: dict[ModuleId, float] | None = None,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    register_status: RegisterStatus | None = None,
    *,
    llm_pass: bool = False,
    knf_warning: str | None = None,
) -> tuple[AnalyzeResponse, str]:
    """Call `POST ai:/analyze`; fall back to the mock analyzer. Returns (response, analyzer).

    In mode `llm` the default call is the fast pass (rules only, findings that need the model
    come back `queued`); `llm_pass=True` is the slow call from the `llm` queue.
    """
    settings = settings or get_settings()
    if settings.ai_mode == "mock":
        return mock_analyze(post, firm_matches), "mock"
    request = AnalyzeRequest(
        post=post,
        render=render,
        firm_matches=firm_matches,
        mode=settings.ai_mode,
        thresholds=thresholds,
        register_status=register_status,
        defer_llm=settings.ai_mode == "llm" and not llm_pass,
        embed=not llm_pass,
        knf_warning=knf_warning,
    )
    timeout = settings.llm_review_timeout_s if llm_pass else settings.ai_timeout_s
    try:
        with httpx.Client(base_url=settings.ai_url, timeout=timeout, transport=transport) as client:
            response = client.post(
                "/analyze",
                content=request.model_dump_json(),
                headers={"content-type": "application/json"},
            )
            response.raise_for_status()
            return AnalyzeResponse.model_validate_json(response.content), "ai"
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("ai service unavailable (%s); using the mock analyzer", exc)
        return mock_analyze(post, firm_matches), "mock"


def embed(
    texts: list[str],
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> EmbedResponse | None:
    """Call `POST ai:/embed`; None when the service or Ollama cannot embed right now."""
    settings = settings or get_settings()
    if settings.ai_mode == "mock" or not texts:
        return None
    try:
        with httpx.Client(
            base_url=settings.ai_url, timeout=settings.ai_timeout_s, transport=transport
        ) as client:
            response = client.post("/embed", json={"texts": texts})
            response.raise_for_status()
            return EmbedResponse.model_validate_json(response.content)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("embedding backfill skipped: %s", exc)
        return None
