from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from investwatch_ai.llm import LLMError, OllamaClient, verify_quote


class Verdict(BaseModel):
    label: str
    score: float


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def _client(handler: Any, sleeps: list[float] | None = None) -> OllamaClient:
    slept = sleeps if sleeps is not None else []
    return OllamaClient(
        "http://ollama:11434",
        timeout_s=5,
        retries=3,
        backoff_s=0.5,
        transport=httpx.MockTransport(handler),
        sleep=slept.append,
    )


def test_chat_json_sends_schema_and_parses_valid_json() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        seen.append(json.loads(request.content))
        return _chat_response('{"label": "fail", "score": 0.8}')

    out = _client(handler).chat_json("gemma3:4b", "system", "user", Verdict)
    assert out == Verdict(label="fail", score=0.8)
    body = seen[0]
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    assert body["format"] == Verdict.model_json_schema()
    assert body["options"]["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_chat_json_retries_invalid_json_then_succeeds() -> None:
    replies = iter(["not json at all", '{"label": 1}', '{"label": "pass", "score": 0.1}'])
    sleeps: list[float] = []
    out = _client(lambda r: _chat_response(next(replies)), sleeps).chat_json("m", "s", "u", Verdict)
    assert out.label == "pass"
    assert sleeps == [0.5, 1.0]


def test_chat_json_gives_up_after_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _chat_response("{broken")

    with pytest.raises(LLMError):
        _client(handler).chat_json("m", "s", "u", Verdict)
    assert calls == 3


def test_chat_json_retries_server_errors_and_transport_errors() -> None:
    attempts = iter(["boom", "503", "ok"])

    def handler(request: httpx.Request) -> httpx.Response:
        step = next(attempts)
        if step == "boom":
            raise httpx.ConnectError("refused", request=request)
        if step == "503":
            return httpx.Response(503, text="loading model")
        return _chat_response('{"label": "na", "score": 0}')

    assert _client(handler).chat_json("m", "s", "u", Verdict).label == "na"


def test_chat_json_does_not_retry_client_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMError, match="404"):
        _client(handler).chat_json("m", "s", "u", Verdict)
    assert calls == 1


def test_embed_calls_api_embed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        body = json.loads(request.content)
        assert body == {"model": "bge-m3", "input": ["a", "b"]}
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    assert _client(handler).embed("bge-m3", ["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_embed_rejects_wrong_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    with pytest.raises(LLMError):
        _client(handler).embed("bge-m3", ["a", "b"])


def test_verify_quote() -> None:
    text = "Wisła Capital S.A. jest nadzorowany przez KNF – Twoje pieniądze są bezpieczne."
    assert verify_quote("nadzorowany przez KNF – Twoje pieniądze są bezpieczne", text)
    # en dash in the text, hyphen in the model output
    assert verify_quote("nadzorowany przez KNF - Twoje pieniądze są bezpieczne", text)
    assert verify_quote("  NADZOROWANY przez knf ", text)
    assert not verify_quote("gwarantujemy zysk 50% rocznie", text)
    assert not verify_quote("", text)


def test_chat_json_usage_reports_tokens_and_disables_thinking() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"label": "fail", "score": 0.9}'},
                "prompt_eval_count": 670,
                "eval_count": 120,
            },
        )

    out, usage = _client(handler).chat_json_usage("gemma4:e2b-it-qat", "s", "u", Verdict)
    assert out.label == "fail"
    assert (usage.model, usage.prompt_tokens, usage.output_tokens) == (
        "gemma4:e2b-it-qat",
        670,
        120,
    )
    assert usage.ms >= 0
    assert seen[0]["think"] is False


def test_timeout_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError, match="timed out"):
        _client(handler).chat_json("m", "s", "u", Verdict)
    assert len(calls) == 1


def test_time_budget_is_shared_by_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _chat_response("{nope")

    client = OllamaClient(
        "http://x",
        timeout_s=0.05,
        retries=50,
        backoff_s=0.02,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMError):
        client.chat_json("m", "s", "u", Verdict)
    assert 1 <= len(calls) < 50


def test_embed_usage_returns_token_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]], "prompt_eval_count": 42})

    vectors, tokens = _client(handler).embed_usage("bge-m3", ["a"])
    assert vectors == [[1.0, 0.0]] and tokens == 42


def test_has_model_checks_pulled_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest"}]})

    client = _client(handler)
    assert client.has_model("bge-m3")
    assert not client.has_model("gemma4:e2b-it-qat")
