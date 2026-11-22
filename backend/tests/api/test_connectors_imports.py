from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from investwatch.main import app


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_connectors_show_what_is_missing(client: TestClient) -> None:
    for path in ("/api/connectors", "/api/sources/connectors"):
        infos = {c["name"]: c for c in client.get(path).json()}
        assert infos["youtube"]["status"] == "needs_credentials"
        assert infos["youtube"]["requires"] == ["YOUTUBE_API_KEY"]
        assert infos["tiktok"]["status"] == "needs_approval"
        assert infos["web"]["status"] == "ready" and infos["web"]["access_mode"] == "crawler"
        assert infos["meta_ad_library"]["how_to"]


def test_sources_carry_connector_status_and_run_is_refused(client: TestClient) -> None:
    created = client.post(
        "/api/sources", json={"name": "yt", "collector": "youtube", "target": "search:1:x"}
    ).json()
    assert created["connector_status"] == "needs_credentials"
    assert created["access_mode"] == "official_api"
    listed = {s["collector"]: s for s in client.get("/api/sources").json()}
    assert listed["sample"]["connector_status"] == "ready"
    r = client.post(f"/api/sources/{created['id']}/run")
    assert r.status_code == 409
    assert r.json()["detail"]["requires"] == ["YOUTUBE_API_KEY"]
    assert "Google Cloud" in r.json()["detail"]["how_to"]


def test_tick_skips_sources_without_credentials(client: TestClient) -> None:
    from investwatch.jobs.tasks import tick_sources

    client.post("/api/sources", json={"name": "meta", "collector": "meta_ad_library",
                                      "target": "XTB", "cron": "* * * * *"})  # fmt: skip
    queued = tick_sources()
    ids = {s["id"]: s["collector"] for s in client.get("/api/sources").json()}
    assert all(ids[q] != "meta_ad_library" for q in queued)


def test_sources_of_removed_collectors_are_disabled_and_never_run(client: TestClient) -> None:
    from investwatch.collectors.policy import REMOVED_REASON
    from investwatch.db import repo
    from investwatch.db.session import session_scope
    from investwatch.jobs.tasks import scrape_source, tick_sources

    # Rows like these survive in databases created before the compliance clean-up (#17).
    with session_scope() as session:
        old = repo.create_source(
            session, name="old search", collector="search", target="forex", cron="* * * * *"
        )
    listed = {s["id"]: s for s in client.get("/api/sources").json()}
    assert listed[str(old.id)]["connector_status"] == "disabled"
    assert listed[str(old.id)]["connector_reason"] == REMOVED_REASON
    assert all(s["connector_reason"] is None for s in listed.values() if s["collector"] == "web")

    r = client.post(f"/api/sources/{old.id}/run")
    assert r.status_code == 409
    assert r.json()["detail"]["how_to"] == REMOVED_REASON
    assert str(old.id) not in tick_sources()
    assert scrape_source(str(old.id))["skipped"] == "disabled"
    with session_scope() as session:
        assert repo.list_runs(session, old.id) == []


def test_import_file(client: TestClient) -> None:
    ads = {"data": [{"id": "77", "page_name": "Broker", "ad_creative_bodies": ["Bonus 500 zł"]}]}
    r = client.post(
        "/api/imports",
        data={"format": "meta_ads_json", "provenance_note": "eksport z Biblioteki reklam"},
        files={"file": ("ads.json", json.dumps(ads).encode(), "application/json")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["items"] == 1 and body["created"] == 1 and len(body["sha256"]) == 64
    post = client.get(f"/api/posts/{body['post_ids'][0]}")
    assert post.status_code in {200, 404}
    bad = client.post(
        "/api/imports", data={"format": "exe"}, files={"file": ("a", b"[]", "text/plain")}
    )
    assert bad.status_code == 422


def test_submission_and_platform_check(client: TestClient) -> None:
    r = client.post(
        "/api/submissions",
        data={"url": "https://www.tiktok.com/@ktos/video/1", "text": "Kod promocyjny ABC"},
    )
    assert r.status_code == 201 and r.json()["created"] == 1
    refused = client.post("/api/check", json={"url": "https://www.facebook.com/somepage/posts/1"})
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["code"] == "platform_url" and "wklej treść" in detail["message"]
    assert "/api/" not in detail["message"]
    yt = client.post("/api/check", json={"url": "https://www.youtube.com/watch?v=ya9Q0A8UB4U"})
    assert yt.status_code == 409
