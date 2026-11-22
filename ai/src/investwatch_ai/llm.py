"""Ollama HTTP client: JSON-schema chat with validation and retries, embeddings, quote checks."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

QUOTE_MIN_SCORE = 90.0
_DASHES = re.compile("[‐-―−]")
_QUOTES = re.compile("[“”„«»‘’‚]")
_WS = re.compile(r"\s+")


class LLMError(RuntimeError):
    """Ollama did not return a usable answer (after retries)."""


class _RetryableError(Exception):
    pass


class Usage(BaseModel):
    """Token counts and wall time of one Ollama call (from its response metadata)."""

    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    ms: float = 0.0


class OllamaClient:
    """Minimal synchronous Ollama client; callers decide how to degrade on `LLMError`.

    `timeout_s` is a hard budget per call, shared by all retries: on CPU a slow model must not
    hold a worker for retries x timeout. A timeout is not retried.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 120.0,
        retries: int = 3,
        backoff_s: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport
        )
        self._timeout_s = timeout_s
        self._retries = max(1, retries)
        self._backoff_s = backoff_s
        self._sleep = sleep

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._http.close()

    def _with_retries(
        self,
        what: str,
        attempt: Callable[[float], T],
        budget_s: float | None = None,
        retries: int | None = None,
    ) -> T:
        """Run `attempt(remaining_s)` until it succeeds, retries run out or the budget is spent."""
        deadline = time.monotonic() + (budget_s or self._timeout_s)
        tries = max(1, retries or self._retries)
        last: Exception | None = None
        for i in range(tries):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return attempt(remaining)
            except _RetryableError as exc:
                last = exc
                log.warning("ollama %s attempt %d/%d failed: %s", what, i + 1, tries, exc)
                if i + 1 < tries:
                    self._sleep(self._backoff_s * 2**i)
        raise LLMError(f"ollama {what} failed after {tries} attempts: {last}")

    def _post(self, path: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        try:
            resp = self._http.post(path, json=payload, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise LLMError(f"ollama {path} timed out after {timeout_s:.0f} s") from exc
        except httpx.TransportError as exc:
            raise _RetryableError(f"{type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            raise _RetryableError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise _RetryableError("response is not JSON") from exc
        if not isinstance(body, dict):
            raise _RetryableError("response is not a JSON object")
        return body

    def chat_json(self, model: str, system: str, user: str, schema: type[T]) -> T:
        """Ask for a JSON answer constrained by `schema` and validate it."""
        return self.chat_json_usage(model, system, user, schema)[0]

    def chat_json_usage(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        format_schema: dict[str, Any] | None = None,
    ) -> tuple[T, Usage]:
        """Like `chat_json`, plus token counts and wall time of the successful call.

        `format_schema` (default: `schema`'s JSON schema) is what Ollama constrains output to;
        it may be stricter than `schema`, which validates the answer.

        Invalid JSON, schema violations, 5xx and transport errors are retried with exponential
        backoff; 4xx errors and timeouts fail immediately.
        """
        started = time.perf_counter()
        usage = Usage(model=model)
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "format": format_schema or schema.model_json_schema(),
            # Reasoning models (Gemma 4) would otherwise spend 3-4x the tokens thinking: on CPU
            # that is 50 s instead of 15 s per review. Ignored by models without thinking.
            "think": False,
            "options": {"temperature": 0, "seed": 42},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        def attempt(remaining_s: float) -> T:
            body = self._post("/api/chat", payload, remaining_s)
            usage.prompt_tokens = _int_or_none(body.get("prompt_eval_count"))
            usage.output_tokens = _int_or_none(body.get("eval_count"))
            content = body.get("message", {}).get("content", "")
            try:
                return schema.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                raise _RetryableError(f"invalid structured output: {str(exc)[:200]}") from exc

        out = self._with_retries("chat", attempt)
        usage.ms = round((time.perf_counter() - started) * 1000, 1)
        return out, usage

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Embed texts with `/api/embed`; one vector per input."""
        return self.embed_usage(model, texts)[0]

    def embed_usage(
        self,
        model: str,
        texts: list[str],
        timeout_s: float | None = None,
        retries: int | None = None,
    ) -> tuple[list[list[float]], int | None]:
        """Embed texts; also return the number of input tokens Ollama reports (all texts).

        `timeout_s` and `retries` override the client's: embeddings sit on the alert's
        critical path, and a dead Ollama must not cost three DNS timeouts there.
        """

        class _EmbedResponse(BaseModel):
            embeddings: list[list[float]]
            prompt_eval_count: int | None = None

        def attempt(remaining_s: float) -> _EmbedResponse:
            body = self._post("/api/embed", {"model": model, "input": texts}, remaining_s)
            try:
                out = _EmbedResponse.model_validate(body)
            except ValidationError as exc:
                raise _RetryableError("invalid embed response") from exc
            if len(out.embeddings) != len(texts):
                raise _RetryableError(f"expected {len(texts)} vectors, got {len(out.embeddings)}")
            return out

        out = self._with_retries("embed", attempt, timeout_s, retries)
        return out.embeddings, out.prompt_eval_count

    def has_model(self, model: str, timeout_s: float = 2.0) -> bool:
        """Return True when `model` is pulled (listed by `/api/tags`)."""
        try:
            resp = self._http.get("/api/tags", timeout=timeout_s)
            names = {m.get("name") for m in resp.json().get("models", [])}
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        return model in names or f"{model}:latest" in names

    def ping(self, timeout_s: float = 1.0) -> bool:
        """Return True when Ollama answers `/api/tags`."""
        try:
            return self._http.get("/api/tags", timeout=timeout_s).status_code == 200
        except httpx.HTTPError:
            return False


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _norm(s: str) -> str:
    s = _DASHES.sub("-", s)
    s = _QUOTES.sub('"', s)
    return _WS.sub(" ", s).strip().casefold()


def verify_quote(quote: str | None, text: str, min_score: float = QUOTE_MIN_SCORE) -> bool:
    """Return True when `quote` occurs in `text` (normalised, fuzzy >= `min_score`)."""
    if not quote or not quote.strip():
        return False
    q, t = _norm(quote), _norm(text)
    if q in t:
        return True
    return len(q) >= 8 and fuzz.partial_ratio(q, t) >= min_score
