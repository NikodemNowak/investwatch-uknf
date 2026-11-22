from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from investwatch.collectors.manual import text_item
from investwatch.core.schemas import Finding, LlmReviewState, RuleResult, RuleStatus
from investwatch.db import repo
from investwatch.pipeline import ai_client
from investwatch.pipeline import analyze as pipeline
from investwatch.pipeline.schemas import AnalyzeResponse, EmbedResponse, LlmUsage
from investwatch.realtime.emitter import MemoryEmitter

TEXT = "Zarabiaj 40% rocznie z naszym portfelem. Najlepszy wynik na rynku."


def _rule(rule_id: str, status: RuleStatus, check_type: str = "text") -> RuleResult:
    return RuleResult.model_validate(
        {
            "rule_id": rule_id,
            "name": f"Reguła {rule_id}",
            "status": status,
            "confidence": 0.0 if status == "unknown" else 1.0,
            "check_type": check_type,
            "weight": 0.9,
            "explanation": "",
            "legal_basis": "art. 44",
            "evidence": [],
        }
    )


def _finding(
    post_id: uuid.UUID, rule_11: RuleStatus, score: float, review: LlmReviewState
) -> Finding:
    return Finding(
        id=uuid.uuid4(),
        post_id=post_id,
        module="m2_risk_disclosure",
        score=score,
        risk_level="high" if score >= 0.7 else "low",
        explanation="",
        quotes=[],
        firm=None,
        firm_match=None,
        advertiser=None,
        rules=[_rule("1", "pass"), _rule("11", rule_11, "llm" if review == "done" else "text")],
        model="rules-v1",
        used_llm=review == "done",
        llm_review=review,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def post_id(db: None, session: Session) -> uuid.UUID:
    result = pipeline.ingest_item(session, text_item(TEXT))
    session.commit()
    return result.post.id


def _fake_ai(
    monkeypatch: pytest.MonkeyPatch, fast: Finding, slow: Finding | None, analyzer: str = "ai"
) -> list[bool]:
    calls: list[bool] = []

    def analyze(*args: Any, llm_pass: bool = False, **kwargs: Any) -> tuple[AnalyzeResponse, str]:
        calls.append(llm_pass)
        if not llm_pass:
            return (
                AnalyzeResponse(
                    findings=[fast],
                    embedding=[0.5] * 1024,
                    lang="pl",
                    timings_ms={"rules": 3.0, "embed": 40.0, "total": 45.0},
                    chars=len(TEXT),
                    tokens=21,
                    embed_model="bge-m3",
                ),
                "ai",
            )
        usage = LlmUsage(model="gemma4:e2b-it-qat", prompt_tokens=600, output_tokens=400, ms=15e3)
        findings = [slow] if slow is not None else []
        return AnalyzeResponse(findings=findings, llm=usage, chars=len(TEXT)), analyzer

    monkeypatch.setattr(ai_client, "analyze", analyze)
    return calls


def test_fast_pass_alerts_and_queues_the_model(
    post_id: uuid.UUID, session: Session, events: MemoryEmitter, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_ai(monkeypatch, _finding(post_id, "unknown", 0.9, "queued"), None)
    outcome = pipeline.analyze_post(post_id)
    assert outcome.review_queued == outcome.finding_ids and outcome.alerted
    assert [e for e, _ in events.events] == ["alert"]
    trace = repo.get_trace(session, post_id)
    assert trace is not None and trace.tokens == 21 and trace.embedding_dim == 1024
    assert trace.llm is None


def test_review_merges_verdict_updates_record_and_emits(
    post_id: uuid.UUID, session: Session, events: MemoryEmitter, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_ai(
        monkeypatch,
        _finding(post_id, "unknown", 0.2, "queued"),
        _finding(post_id, "fail", 0.95, "done"),
    )
    outcome = pipeline.analyze_post(post_id)
    assert not outcome.alerted  # below threshold before the model answers
    finding_id = uuid.UUID(outcome.finding_ids[0])

    result = pipeline.review_finding(finding_id)

    assert calls == [False, True]
    assert result.state == "done" and result.changed_rules == ["11"]
    assert result.alerted  # the model pushed the score over the threshold
    view = repo.get_finding(session, finding_id)
    assert view is not None and view.llm_review == "done" and view.used_llm
    assert {r.rule_id: r.status for r in view.rules}["11"] == "fail"
    assert view.trace is not None and view.trace.llm is not None
    assert view.trace.llm.output_tokens == 400 and view.trace.llm.state == "done"
    assert [e for e, _ in events.events] == ["finding_updated", "alert"]
    assert events.events[0][1]["llm_review"] == "done"
    # A finished review is not repeated.
    assert pipeline.review_finding(finding_id).state == "skipped"


def test_review_without_model_keeps_rules_and_says_unavailable(
    post_id: uuid.UUID, session: Session, events: MemoryEmitter, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_ai(monkeypatch, _finding(post_id, "unknown", 0.9, "queued"), None, analyzer="mock")
    finding_id = uuid.UUID(pipeline.analyze_post(post_id).finding_ids[0])

    result = pipeline.review_finding(finding_id)

    assert result.state == "unavailable" and result.changed_rules == []
    view = repo.get_finding(session, finding_id)
    assert view is not None and view.llm_review == "unavailable" and view.score == 0.9
    assert view.trace is not None and view.trace.llm is not None
    assert view.trace.llm.error == "ai service unreachable"
    assert [e for e, _ in events.events] == ["alert", "finding_updated"]


def test_backfill_embeds_seeded_posts(seeded: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def embed(texts: list[str], *args: Any, **kwargs: Any) -> EmbedResponse:
        return EmbedResponse(model="bge-m3", dim=1024, embeddings=[[0.1] * 1024], tokens=7)

    monkeypatch.setattr(ai_client, "embed", embed)
    from investwatch.db.session import session_scope

    with session_scope() as s:
        missing = len(repo.posts_without_embedding(s, 100))
    assert missing > 0
    assert pipeline.embed_missing_posts(limit=100) == missing
    with session_scope() as s:
        assert repo.posts_without_embedding(s, 100) == []
    assert pipeline.embed_missing_posts() == 0


def test_backfill_stops_when_ollama_is_down(seeded: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_client, "embed", lambda *a, **k: None)
    assert pipeline.embed_missing_posts() == 0
