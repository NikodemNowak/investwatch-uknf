"""`GET /api/system`: every service is listed; failures are reported, never raised."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from investwatch.main import app
from investwatch.status import probe


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    probe.clear_cache()
    with TestClient(app) as c:
        yield c
    probe.clear_cache()


def test_system_status_lists_every_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_redis() -> object:
        raise ConnectionError("redis down")

    monkeypatch.setattr(probe, "_redis", no_redis)
    body = client.get("/api/system").json()
    states = {s["name"]: s["state"] for s in body["services"]}
    assert list(states) == [
        "api", "database", "redis", "minio", "workers", "beat", "ai", "ollama",
    ]  # fmt: skip
    assert states["api"] == "ok" and states["database"] == "ok" and states["minio"] == "ok"
    redis = next(s for s in body["services"] if s["name"] == "redis")
    assert redis["state"] == "down" and "redis down" in redis["detail"]
    # Tests run Celery eagerly with the mock AI.
    assert states["workers"] == "disabled" and states["beat"] == "disabled"
    assert states["ai"] == "disabled" and body["ai"]["mode"] == "mock"


def test_next_run_is_the_earliest_enabled_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "_redis", lambda: (("ok", None), None))
    body = client.get("/api/system").json()
    nxt = body["next_run"]
    sources = [s for s in client.get("/api/sources").json() if s["enabled"] and s["next_run_at"]]
    if sources:
        assert nxt["at"] == min(s["next_run_at"] for s in sources)
    else:
        assert nxt is None


def test_beat_tick_freshness(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime, timedelta

    from investwatch.config import get_settings

    monkeypatch.setenv("CELERY_EAGER", "false")
    get_settings.cache_clear()
    fresh = datetime.now(UTC) - timedelta(seconds=30)
    monkeypatch.setattr(probe, "_redis", lambda: (("ok", None), fresh))
    monkeypatch.setattr(probe, "_workers", lambda: (("ok", "4"), []))
    monkeypatch.setattr(probe, "_next_run", lambda: None)
    monkeypatch.setattr(probe, "_database", lambda: ("ok", "sqlite"))
    status = probe.probe_system()
    beat = next(s for s in status.services if s.name == "beat")
    assert beat.state == "ok"
    monkeypatch.setattr(probe, "_redis", lambda: (("ok", None), fresh - timedelta(hours=1)))
    stale = next(s for s in probe.probe_system().services if s.name == "beat")
    assert stale.state == "down"


@pytest.mark.parametrize(("mode", "state"), [("rules", "ok"), ("llm", "degraded")])
def test_lite_stack_expects_no_llm_worker(
    mode: str, state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docker-compose.lite.yml (AI_MODE=rules) runs no worker-llm: that is not a fault."""
    from investwatch.config import get_settings
    from investwatch.jobs.celery_app import celery_app

    monkeypatch.setenv("AI_MODE", mode)
    monkeypatch.setenv("CELERY_EAGER", "false")
    get_settings.cache_clear()
    queues = ["check", "scrape", "analyze", "maintenance"]
    replies = {"celery@w1": [{"name": q} for q in queues]}

    class Inspect:
        def active_queues(self) -> dict[str, list[dict[str, str]]]:
            return replies

    monkeypatch.setattr(celery_app.control, "inspect", lambda timeout: Inspect())
    (probe_state, _), _ = probe._workers()
    assert probe_state == state
