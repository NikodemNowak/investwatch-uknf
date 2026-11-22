from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from investwatch.collectors.base import MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.web import WebCollector
from investwatch.config import Settings, get_settings
from investwatch.db import repo
from investwatch.main import app
from investwatch.registry import sync as registry_sync
from investwatch.registry.knf import load_snapshot
from investwatch.registry.schemas import RegisterSnapshot


def _offline(_: Settings) -> RegisterSnapshot:
    raise httpx.ConnectError("no network")


def test_live_sync_falls_back_to_snapshot(session: Session) -> None:
    result = registry_sync.sync(session, live=True, fetch=_offline)
    assert result.source == "snapshot" and result.error and "ConnectError" in result.error
    assert result.per_kind["dom_maklerski"] > 0 and result.total > 700
    status = repo.registry_status(session)
    assert status.last_sync is not None and status.last_sync.source == "snapshot"
    assert status.total_active == result.total
    assert set(status.active_per_kind) == {
        "dom_maklerski",
        "bank_maklerski",
        "oddzial_zagraniczny",
        "zagraniczna_bez_oddzialu",
    }
    assert status.fictional >= 2  # demo firms (Aurora Kapitał, Kyrenia Prime)


def test_live_sync_upserts_and_deactivates_removed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = load_snapshot(registry_sync.snapshot_path())
    registry_sync.sync(session, live=False)
    smaller = snapshot.model_copy(update={"records": snapshot.records[:-3]})
    monkeypatch.setattr(registry_sync, "_try_save", lambda *_: None)
    result = registry_sync.sync(session, live=True, fetch=lambda _: smaller)
    assert result.source == "live" and result.error is None
    assert (result.added, result.removed) == (0, 3)
    active = {f.id for f in repo.list_firms(session)}
    assert snapshot.records[-1].firm_id not in active
    assert snapshot.records[0].firm_id in active
    # Brand curation: the register has no website for XTB, brands.json adds it.
    xtb = next(f for f in repo.list_firms(session) if f.name == "XTB S.A.")
    assert "xtb.com" in xtb.domains


@pytest.fixture
def client(seeded: None) -> TestClient:
    return TestClient(app)


def test_firms_search_and_detail(client: TestClient) -> None:
    page = client.get("/api/firms", params={"q": "xtb"}).json()
    names = [i["firm"]["name"] for i in page["items"]]
    assert names[0] == "XTB S.A." and page["total"] >= 2
    item = page["items"][0]
    assert item["source"] == "knf" and item["active"] is True
    # Diacritics-insensitive, finds by alias and trade name.
    assert client.get("/api/firms", params={"q": "slaski"}).json()["total"] >= 1
    assert client.get("/api/firms", params={"q": "Ausprime"}).json()["total"] == 1
    banks = client.get("/api/firms", params={"kind": "bank_maklerski", "limit": 200}).json()
    assert sum(i["source"] == "knf" for i in banks["items"]) == 10  # + 2 fictional fixtures

    detail = client.get(f"/api/firms/{item['firm']['id']}").json()
    assert detail["former_names"] == ["X-TRADE BROKERS DOM MAKLERSKI S.A."]
    assert detail["firm"]["register_url"].startswith("https://www.knf.gov.pl/")
    assert detail["legal_form"] == "S.A." and detail["findings"] == 0
    assert client.get(f"/api/firms/{uuid.uuid4()}").status_code == 404


def test_firm_detail_counts_findings(client: TestClient) -> None:
    kyrenia = "c0000000-0000-4000-8000-000000000007"
    detail = client.get(f"/api/firms/{kyrenia}").json()
    assert detail["findings"] >= 2 and detail["source"] == "demo"
    assert "demo-sites/promo-zloto.html" in detail["firm"]["domains"]


def test_status_and_manual_sync(client: TestClient) -> None:
    status = client.get("/api/firms/status").json()
    assert status["last_sync"]["source"] == "snapshot" and status["total_active"] > 700
    assert status["attribution"].startswith("Źródło: rejestry KNF (knf.gov.pl), stan na 20")
    assert "otwartych danych" in status["legal_basis"]
    r = client.post("/api/firms/sync", params={"live": "false"})
    assert r.status_code == 202
    assert len(client.get("/api/firms/status").json()["history"]) == 2


def test_check_demo_page_of_fictional_firm_is_by_the_firm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, demo_html: dict[str, str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=demo_html["promo-zloto.html"])

    fetcher = PoliteFetcher(get_settings(), MemoryRateLimiter(0), httpx.MockTransport(handler))
    monkeypatch.setattr(
        "investwatch.jobs.tasks.WebCollector",
        lambda name: WebCollector(fetcher, name=name, render=False),
    )
    job = client.post("/api/check", json={"url": "http://demo-sites/promo-zloto.html"}).json()
    finding_ids = client.get(f"/api/check/{job['job_id']}").json()["finding_ids"]
    assert finding_ids
    finding = client.get(f"/api/findings/{finding_ids[0]}").json()
    assert finding["firm_match"]["on"] == "author"
    assert finding["firm"]["name"] == "Kyrenia Prime Ltd"


def test_daily_beat_entry() -> None:
    from investwatch.jobs.beat import BEAT_SCHEDULE

    assert BEAT_SCHEDULE["sync-knf-registry"]["task"] == "investwatch.sync_registry"
