"""Text embeddings: bge-m3 through Ollama, or a deterministic stand-in for mock mode."""

from __future__ import annotations

import hashlib
import logging

import numpy as np

from .llm import LLMError, OllamaClient

log = logging.getLogger(__name__)

MOCK_DIM = 1024
"""Same width as bge-m3, so mock vectors fit the pgvector column."""


def mock_embedding(text: str, dim: int = MOCK_DIM) -> list[float]:
    """Return a unit vector seeded by the text hash: identical text gives identical vectors."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    vec = np.random.default_rng(seed).standard_normal(dim)
    vec /= np.linalg.norm(vec)
    return [float(x) for x in vec]


def embed_texts(texts: list[str], client: OllamaClient, model: str) -> list[list[float]]:
    """Embed with Ollama and L2-normalise, so cosine similarity is a dot product."""
    return embed_texts_usage(texts, client, model)[0]


def embed_texts_usage(
    texts: list[str],
    client: OllamaClient,
    model: str,
    timeout_s: float | None = None,
    retries: int | None = None,
) -> tuple[list[list[float]], int | None]:
    """`embed_texts` plus the input token count Ollama reports."""
    if not texts:
        return [], 0
    vectors, tokens = client.embed_usage(model, texts, timeout_s, retries)
    arr = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / np.where(norms == 0, 1.0, norms)
    return [[float(x) for x in row] for row in arr], tokens


def try_embed(
    text: str, client: OllamaClient | None, model: str, timeout_s: float | None = None
) -> tuple[list[float] | None, int | None]:
    """Embed one text and count its tokens; (None, None) (and a log line) when Ollama is down.

    One attempt only: the backend backfills missing embeddings later (`embed_missing_posts`).
    """
    if client is None:
        return None, None
    try:
        vectors, tokens = embed_texts_usage([text], client, model, timeout_s, retries=1)
    except LLMError as exc:
        log.warning("embedding skipped: %s", exc)
        return None, None
    return vectors[0], tokens
