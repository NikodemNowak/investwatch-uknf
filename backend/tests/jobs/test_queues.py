from __future__ import annotations

import json
from typing import Any

import pytest
import redis

from investwatch.jobs import tasks
from investwatch.jobs.celery_app import create_app
from investwatch.jobs.queues import (
    CHECK_QUEUE,
    LLM_PRIORITY_QUEUE,
    LLM_QUEUE,
    queue_position,
    review_queue,
)
from investwatch.pipeline.schemas import AnalysisOutcome


def _msg(finding_id: str, eta: str | None = None) -> bytes:
    headers = {"argsrepr": f"('{finding_id}',)", "eta": eta}
    return json.dumps({"headers": headers, "body": "e30="}).encode()


class FakeRedis:
    """Just the commands `queue_position` uses; lists are in Redis order (LPUSH = index 0)."""

    def __init__(
        self,
        lists: dict[str, list[str]],
        running: list[tuple[str, str]],
        retrying: list[str] | None = None,
    ) -> None:
        self.lists = {name: [_msg(f) for f in ids] for name, ids in lists.items()}
        held = [(_msg(f), q) for f, q in running] + [
            (_msg(f, eta="2026-11-21T20:00:00+00:00"), LLM_QUEUE) for f in retrying or []
        ]
        self.unacked = [json.dumps([json.loads(m), "", q]).encode() for m, q in held]

    def lrange(self, name: str, start: int, end: int) -> list[bytes]:
        return self.lists.get(name, [])

    def hvals(self, name: str) -> list[bytes]:
        return self.unacked


def test_review_queue_routes_analyst_material_first() -> None:
    assert review_queue(True) == LLM_PRIORITY_QUEUE
    assert review_queue(False) == LLM_QUEUE


def test_priority_review_counts_only_priority_and_running() -> None:
    # Taken from the right: "p-old" goes before "p-new"; the batch backlog does not count.
    client = FakeRedis(
        {LLM_PRIORITY_QUEUE: ["p-new", "p-old"], LLM_QUEUE: ["b1", "b2", "b3"]},
        running=[("b0", LLM_QUEUE)],
        retrying=["r1", "r2"],  # waiting for a retry countdown: not ahead of anyone
    )
    pos = queue_position("p-new", client)  # type: ignore[arg-type]
    assert (pos.state, pos.queue, pos.ahead, pos.waiting) == ("queued", LLM_PRIORITY_QUEUE, 2, 5)
    assert queue_position("p-old", client).ahead == 1  # type: ignore[arg-type]


def test_batch_review_waits_for_priority_queue() -> None:
    client = FakeRedis({LLM_PRIORITY_QUEUE: ["p"], LLM_QUEUE: ["b1", "b2"]}, running=[])
    pos = queue_position("b1", client)  # type: ignore[arg-type]
    assert (pos.state, pos.queue, pos.ahead) == ("queued", LLM_QUEUE, 2)


def test_running_and_unknown_reviews() -> None:
    client = FakeRedis({}, running=[("f", LLM_PRIORITY_QUEUE), ("x", "analyze")])
    assert queue_position("f", client).state == "running"  # type: ignore[arg-type]
    assert queue_position("gone", client).state == "unknown"  # type: ignore[arg-type]


def test_redis_down_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    assert queue_position("f").state == "unknown"


def test_unreachable_client_is_unknown() -> None:
    class Down:
        def lrange(self, *_: Any) -> list[bytes]:
            raise redis.ConnectionError("down")

    assert queue_position("f", Down()).state == "unknown"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("job_id", "priority", "queue"),
    [
        ("job", False, LLM_PRIORITY_QUEUE),
        (None, True, LLM_PRIORITY_QUEUE),
        (None, False, LLM_QUEUE),
    ],
)
def test_analyze_post_routes_reviews(
    monkeypatch: pytest.MonkeyPatch, job_id: str | None, priority: bool, queue: str
) -> None:
    outcome = AnalysisOutcome(post_id="p", review_queued=["f1"], analyzer="mock")
    monkeypatch.setattr(tasks.pipeline, "analyze_post", lambda *_a, **_k: outcome)
    monkeypatch.setattr(tasks, "emit_job", lambda _e: None)
    sent: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setattr(
        tasks.review_finding, "apply_async", lambda args, **kw: sent.append((args, kw))
    )
    tasks.analyze_post.run("00000000-0000-0000-0000-000000000001", job_id, priority)
    assert sent == [(("f1",), {"queue": queue})]


def test_queue_order_strategy_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_QUEUE_ORDER", "priority")
    from investwatch.config import get_settings

    get_settings.cache_clear()
    assert create_app().conf.broker_transport_options == {"queue_order_strategy": "priority"}


def test_check_runs_on_its_own_queue() -> None:
    routes = tasks.celery_app.conf.task_routes
    assert routes["investwatch.check_url"] == {"queue": CHECK_QUEUE}
    assert routes["investwatch.scrape_source"] == {"queue": "scrape"}
