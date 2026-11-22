"""FastAPI app of the `ai` service: /health, /embed, /analyze."""

from __future__ import annotations

import logging
from functools import cache
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import Field

from .analyze import AnalyzeRequest, AnalyzeResponse, analyze
from .config import Settings, get_settings
from .embed import MOCK_DIM, embed_texts_usage, mock_embedding
from .llm import LLMError, OllamaClient
from .rules import M2_RULE_IDS, load_lexicon, load_rules_file
from .schemas import ContractModel

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="InvestWatch AI", version="0.1.0")

SettingsDep = Annotated[Settings, Depends(get_settings)]


@cache
def _client(base_url: str, timeout_s: float, retries: int, backoff_s: float) -> OllamaClient:
    return OllamaClient(base_url, timeout_s=timeout_s, retries=retries, backoff_s=backoff_s)


def get_client(settings: SettingsDep) -> OllamaClient | None:
    """Shared Ollama client, or None in mock mode and in the lite stack (rules, no embeddings)."""
    if settings.ai_mode == "mock" or not uses_ollama(settings, settings.ai_mode):
        return None
    return _client(
        settings.ollama_url, settings.llm_timeout_s, settings.llm_retries, settings.llm_backoff_s
    )


def uses_ollama(settings: Settings, mode: str) -> bool:
    """Whether a request in `mode` talks to Ollama at all (LLM review or bge-m3 embeddings)."""
    return mode == "llm" or (mode == "rules" and settings.embed_enabled)


ClientDep = Annotated[OllamaClient | None, Depends(get_client)]


class EmbedRequest(ContractModel):
    """Body of `POST /embed`."""

    texts: list[str] = Field(min_length=1, max_length=64)


class EmbedResponse(ContractModel):
    """Response of `POST /embed`: L2-normalised vectors."""

    model: str
    dim: int
    embeddings: list[list[float]]
    tokens: int | None = None
    """Input tokens of all texts together, as counted by the embedding model."""


@app.get("/health")
def health(settings: SettingsDep, client: ClientDep) -> dict[str, Any]:
    """Liveness plus model status; Ollama being down does not make the service unhealthy.

    `llm_ready` / `embed_ready` are false while `ollama-init` is still pulling the models.
    """
    rules = load_rules_file()
    load_lexicon()
    up = client is not None and client.ping()
    return {
        "status": "ok",
        "mode": settings.ai_mode,
        "rules_version": rules.version,
        "rules": len(M2_RULE_IDS),
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
        "ollama": "disabled" if client is None else ("up" if up else "down"),
        "llm_ready": bool(up and client is not None and client.has_model(settings.llm_model)),
        "embed_ready": bool(up and client is not None and client.has_model(settings.embed_model)),
    }


@app.post("/embed")
def embed(req: EmbedRequest, settings: SettingsDep, client: ClientDep) -> EmbedResponse:
    """Embed texts with bge-m3 (or deterministic mock vectors)."""
    if not settings.embed_enabled:
        raise HTTPException(status_code=503, detail="embeddings disabled (EMBED_ENABLED=false)")
    if client is None:
        vectors = [mock_embedding(t) for t in req.texts]
        return EmbedResponse(model="mock", dim=MOCK_DIM, embeddings=vectors)
    try:
        vectors, tokens = embed_texts_usage(
            req.texts, client, settings.embed_model, settings.embed_timeout_s
        )
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return EmbedResponse(
        model=settings.embed_model, dim=len(vectors[0]), embeddings=vectors, tokens=tokens
    )


@app.post("/analyze")
def analyze_post(req: AnalyzeRequest, settings: SettingsDep, client: ClientDep) -> AnalyzeResponse:
    """Analyse one post: findings per module, embedding, language and timings."""
    if req.mode == "mock":
        client = None
    elif client is None and req.mode is not None and uses_ollama(settings, req.mode):
        client = _client(
            settings.ollama_url,
            settings.llm_timeout_s,
            settings.llm_retries,
            settings.llm_backoff_s,
        )
    return analyze(req, settings, client)
