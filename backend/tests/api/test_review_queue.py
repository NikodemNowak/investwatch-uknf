from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from investwatch.api import findings as findings_api
from investwatch.db import session as db_session
from investwatch.db.models import FindingRow
from investwatch.jobs.queues import ReviewQueuePosition
from investwatch.main import app


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_review_queue_only_for_queued_reviews(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = client.get("/api/findings", params={"page_size": 100}).json()["items"]
    queued, other = items[0], items[1]
    with db_session.session_scope() as s:
        s.execute(update(FindingRow).values(llm_review="none"))
        s.execute(
            update(FindingRow)
            .where(FindingRow.id == uuid.UUID(queued["id"]))
            .values(llm_review="queued")
        )
    monkeypatch.setattr(
        findings_api,
        "queue_position",
        lambda fid: ReviewQueuePosition(state="queued", queue="llm_priority", ahead=2, waiting=9),
    )
    assert client.get(f"/api/findings/{other['id']}/review-queue").json()["state"] == "unknown"
    body = client.get(f"/api/findings/{queued['id']}/review-queue").json()
    assert (body["state"], body["ahead"]) == ("queued", 2)
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/findings/{missing}/review-queue").status_code == 404


def test_submission_skips_the_batch_analyze_queue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from investwatch.api import imports

    sent: list[dict[str, object]] = []
    monkeypatch.setattr(
        imports.analyze_post, "apply_async", lambda *a, **kw: sent.append({"a": a, **kw})
    )
    r = client.post("/api/submissions", data={"text": "Gwarantowany zysk 30% miesięcznie"})
    assert r.status_code == 201
    assert sent and sent[0]["queue"] == "check" and sent[0]["a"][1] == {"priority": True}
