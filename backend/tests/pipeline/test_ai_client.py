from __future__ import annotations

import json

import httpx

from investwatch.collectors.sample import load_findings, load_posts
from investwatch.config import Settings
from investwatch.pipeline.ai_client import analyze
from investwatch.pipeline.schemas import AnalyzeRequest, AnalyzeResponse


def test_uses_ai_service_when_available() -> None:
    post = load_posts()[2]
    finding = load_findings()[4]
    seen: list[AnalyzeRequest] = []
    request_keys: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(AnalyzeRequest.model_validate_json(request.content))
        request_keys.append(json.loads(request.content))
        body = AnalyzeResponse(findings=[finding], embedding=[0.1] * 4, lang="pl")
        return httpx.Response(200, content=body.model_dump_json())

    thresholds = {"m2_risk_disclosure": 0.7}
    response, analyzer = analyze(
        post, None, [], thresholds, Settings(ai_mode="rules"), httpx.MockTransport(handler)
    )
    assert analyzer == "ai"
    assert response.findings == [finding]
    assert seen[0].mode == "rules" and seen[0].post == post
    assert seen[0].thresholds == thresholds
    assert set(request_keys[0]) == {
        "post",
        "render",
        "firm_matches",
        "mode",
        "thresholds",
        "register_status",
        "defer_llm",
        "embed",
        "knf_warning",
    }
    assert request_keys[0]["knf_warning"] is None
    assert request_keys[0]["defer_llm"] is False  # rules mode never queues the model


def test_sends_the_warning_list_entity() -> None:
    seen: list[AnalyzeRequest] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(AnalyzeRequest.model_validate_json(request.content))
        return httpx.Response(200, content=AnalyzeResponse(findings=[]).model_dump_json())

    analyze(
        load_posts()[0],
        None,
        [],
        None,
        Settings(ai_mode="rules"),
        httpx.MockTransport(handler),
        knf_warning="Quantumlux Group",
    )
    assert seen[0].knf_warning == "Quantumlux Group"


def test_falls_back_to_mock_when_ai_is_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    post = load_posts()[0]
    response, analyzer = analyze(
        post, None, [], None, Settings(ai_mode="llm"), httpx.MockTransport(handler)
    )
    assert analyzer == "mock"
    assert response.findings


def test_falls_back_on_invalid_response() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"nope": 1}))
    _, analyzer = analyze(load_posts()[0], None, [], None, Settings(ai_mode="rules"), transport)
    assert analyzer == "mock"
