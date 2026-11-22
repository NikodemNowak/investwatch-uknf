"""Platform items through the pipeline: raw JSON in object storage, honest run status."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from investwatch.collectors import registry
from investwatch.collectors.platform import envelope, failed_item
from investwatch.collectors.schemas import CollectedItem
from investwatch.db import repo
from investwatch.jobs.tasks import scrape_source
from investwatch.pipeline.analyze import ingest_item
from investwatch.storage.minio import get_store


def _video() -> CollectedItem:
    return CollectedItem(
        platform="youtube",
        collector="youtube",
        external_id="abc123def45",
        url="https://www.youtube.com/watch?v=abc123def45",
        author="Kanał",
        text="Kod promocyjny XTB: START #reklama",
        raw=envelope("youtube", "https://www.youtube.com/watch?v=abc123def45", "q", {"id": "x"}),
    )


def test_raw_json_is_stored_as_the_raw_artefact(session: Session) -> None:
    result = ingest_item(session, _video())
    key = result.post.html_key
    assert key == f"raw/{result.post.id}.json"
    stored = json.loads(get_store().get_bytes(key) or b"{}")
    assert stored["collector"] == "youtube" and stored["data"] == {"id": "x"}
    assert stored["source_url"].endswith("abc123def45") and stored["fetched_at"]


class _Fixed:
    name = "fixed"

    def __init__(self, items: list[CollectedItem]) -> None:
        self.items = items

    def collect(self, target: str) -> list[CollectedItem]:
        return self.items


@pytest.mark.parametrize(
    ("items", "status", "seen"),
    [
        ([failed_item("tiktok", "tiktok", "x", "blocked", "login wall")], "blocked", 1),
        ([failed_item("youtube", "youtube", "x", "error", "boom")], "error", 1),
        ([_video()], "ok", 1),
    ],
)
def test_scrape_run_records_status_and_counts(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    items: list[CollectedItem],
    status: str,
    seen: int,
) -> None:
    monkeypatch.setitem(registry.COLLECTORS, "fixed", lambda: _Fixed(items))
    source = repo.create_source(session, name="s", collector="fixed", target="x", cron="0 * * * *")
    session.commit()
    result = scrape_source(str(source.id))
    assert result["status"] == status and result["seen"] == seen
    [run] = repo.list_runs(session, source.id)
    assert run.status == status and run.items_seen == seen
    if status != "ok":
        assert run.error


def test_refresh_youtube_deletes_removed_videos(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from investwatch.collectors.official import youtube_api
    from investwatch.config import get_settings
    from investwatch.jobs.tasks import refresh_youtube

    assert refresh_youtube()["skipped"]
    stored = ingest_item(session, _video()).post
    session.commit()
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    get_settings.cache_clear()
    monkeypatch.setattr(youtube_api.YouTubeApiCollector, "refresh", lambda self, ids: ([], ids))
    assert refresh_youtube() == {"refreshed": 0, "removed": 1}
    session.expire_all()
    post = repo.get_post(session, stored.id)
    assert post is not None and post.text == "" and post.fetch_status == "no_text"
