from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Must be set before any `investwatch` import: settings and the Celery app are module-level.
os.environ.update(
    {
        "APP_DATA_DIR": str(REPO / "data"),
        "CELERY_EAGER": "true",
        "REALTIME_BACKEND": "memory",
        "STORAGE_BACKEND": "memory",
        "AI_MODE": "mock",
        "COLLECTOR_MIN_INTERVAL_S": "0",
        "RENDER_ENABLED": "false",
        "DATABASE_URL": "sqlite:///:memory:",
    }
)

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from investwatch.config import get_settings  # noqa: E402
from investwatch.db import session as db_session  # noqa: E402
from investwatch.realtime import emitter  # noqa: E402
from investwatch.storage import minio  # noqa: E402


def _reset_caches() -> None:
    from investwatch.collectors import base
    from investwatch.collectors.discovery import cache
    from investwatch.collectors.official import youtube_api

    base.get_cooldown.cache_clear()
    base.get_rate_limiter.cache_clear()
    cache.get_cache.cache_clear()
    youtube_api.get_quota.cache_clear()
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    emitter.get_emitter.cache_clear()
    minio.get_store.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_process_state() -> Iterator[None]:
    """Cooldowns, quota counters and caches are per process: never leak between tests."""
    _reset_caches()
    yield


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh, migrated SQLite database per test."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    _reset_caches()
    from investwatch.seed import run_migrations

    run_migrations()
    yield
    db_session.get_engine().dispose()
    _reset_caches()


@pytest.fixture
def session(db: None) -> Iterator[Session]:
    with db_session.session_scope() as s:
        yield s


RENDER_FIXTURE_KEY = "render/a0000000-0000-4000-8000-000000000003.json"
SHOTS_FIXTURE_PREFIX = "shots/a0000000-0000-4000-8000-000000000003"


def load_contract_fixtures(session: Session) -> int:
    """Test data only: the hand-written posts and findings of `data/fixtures` (+ render, shots).

    Production seeding never inserts findings; the demo replays real material instead.
    """
    from investwatch.collectors import sample
    from investwatch.db import repo
    from investwatch.pipeline.dedup import content_hash

    for post in sample.load_posts():
        # Fixture hashes may predate our normalisation; dedup needs the pipeline's definition.
        repo.upsert_post(session, post.model_copy(update={"content_hash": content_hash(post.text)}))
    findings = repo.save_findings(session, sample.load_findings())
    store = minio.get_store()
    snapshot = sample.load_render_snapshot().model_dump_json().encode()
    store.put_bytes(RENDER_FIXTURE_KEY, snapshot, "application/json")
    for png in sorted((get_settings().fixtures_dir / "shots").glob("*.png")):
        store.put_bytes(f"{SHOTS_FIXTURE_PREFIX}/{png.name}", png.read_bytes(), "image/png")
    return len(findings)


@pytest.fixture
def seeded(db: None) -> None:
    from investwatch.seed import seed_base

    with db_session.session_scope() as s:
        # Fixture findings embed old copies of their firms; the register sync then wins.
        load_contract_fixtures(s)
        seed_base(s)


@pytest.fixture
def events() -> emitter.MemoryEmitter:
    em = emitter.get_emitter()
    assert isinstance(em, emitter.MemoryEmitter)
    return em


@pytest.fixture
def demo_html() -> dict[str, str]:
    base = REPO / "demo-sites" / "public"
    return {p.name: p.read_text(encoding="utf-8") for p in base.glob("*.html")}
