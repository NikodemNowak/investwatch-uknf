""" "Pod maską": fetch trace, stored objects with SHA-256, Celery task ids and model parts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from investwatch.collectors import registry
from investwatch.collectors.base import MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.web import WebCollector
from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.jobs.tasks import scrape_source
from investwatch.main import app
from investwatch.provenance.build import classifier_note, model_parts
from investwatch.storage.minio import get_store


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    ("model", "rules", "llm", "clf", "variant", "mock"),
    [
        ("rules-v2", "rules-v2", None, None, None, False),
        ("rules-v2+lr-v1-embedding", "rules-v2", None, "lr-v1", "embedding", False),
        ("gemma4:e2b-it-qat+rules-v2+lr-v1-lexicon", "rules-v2", "gemma4:e2b-it-qat", "lr-v1",
         "lexicon", False),
        ("mock+rules-v1", "rules-v1", None, None, None, True),
        ("mock-rules-v0", "mock-rules-v0", None, None, None, True),
    ],
)  # fmt: skip
def test_model_parts(
    model: str, rules: str, llm: str | None, clf: str | None, variant: str | None, mock: bool
) -> None:
    parts = model_parts(model)
    assert (parts.rules_version, parts.llm_model, parts.classifier) == (rules, llm, clf)
    assert (parts.classifier_variant, parts.mock) == (variant, mock)


def test_classifier_note_is_cut_at_the_sentence_end() -> None:
    text = (
        "Elementy doradztwa: a, b. Klasyfikator (embedding bge-m3 + leksykon): p = 0.83; "
        "wkład w logit: rekomendacja +1.2, embedding +0.8. Podmiot figuruje na liście."
    )
    assert classifier_note(text) == (
        "Klasyfikator (embedding bge-m3 + leksykon): p = 0.83; "
        "wkład w logit: rekomendacja +1.2, embedding +0.8."
    )
    assert classifier_note("Naruszenia: brak.") is None


def _web_collector(html: str) -> WebCollector:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\nCrawl-delay: 0")
        return httpx.Response(200, text=html)

    fetcher = PoliteFetcher(get_settings(), MemoryRateLimiter(0), httpx.MockTransport(handler))
    return WebCollector(fetcher, name="web", render=False)


def test_trace_of_a_crawled_page(
    client: TestClient,
    session: Session,
    demo_html: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = _web_collector(demo_html["hidden-risk.html"])
    monkeypatch.setitem(registry.COLLECTORS, "web", lambda: collector)
    source = repo.create_source(
        session,
        name="Strona demo",
        collector="web",
        target="http://demo-sites/hidden-risk.html",
        cron="*/30 * * * *",
    )
    session.commit()
    assert scrape_source.delay(str(source.id)).get()["status"] == "ok"

    found = client.get("/api/findings", params={"q": "demo-sites"}).json()["items"]
    finding = next(f for f in found if f["post"]["url"].endswith("hidden-risk.html"))
    body = client.get(f"/api/findings/{finding['id']}/trace").json()

    assert body["source"]["name"] == "Strona demo" and body["source"]["cron"] == "*/30 * * * *"
    job = body["collect_job"]
    assert job["task"] == "investwatch.scrape_source" and job["queue"] == "scrape"
    assert job["task_id"] and job["run_id"]
    fetch = body["fetch"]
    assert "InvestWatchBot" in fetch["user_agent"]
    assert fetch["robots"] == "allowed" and fetch["http_status"] == 200
    assert fetch["proxy"] is None and fetch["access_mode"] == "crawler"
    assert fetch["legal_basis"].startswith("art. 26")

    html = next(o for o in body["objects"] if o["kind"] == "html")
    stored = get_store().get_bytes(html["key"])
    assert stored is not None and html["sha256"] == hashlib.sha256(stored).hexdigest()
    assert {o["kind"] for o in body["objects"]} >= {"html", "raw"}

    trace = body["trace"]
    assert trace["task"]["queue"] == "analyze" and trace["task"]["task_id"]
    assert "rules-" in trace["rules_version"]
    assert body["model"]["rules_version"] == trace["rules_version"]
    assert body["similar"] == [] and body["similar_available"] is False  # SQLite: no pgvector


def test_trace_of_a_fixture_finding_has_no_fetch(client: TestClient) -> None:
    fid = client.get("/api/findings").json()["items"][0]["id"]
    body = client.get(f"/api/findings/{fid}/trace").json()
    assert body["fetch"] is None and body["collect_job"] is None
    assert body["content_hash"]
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/findings/{missing}/trace").status_code == 404


def test_minio_store_keeps_the_hash_in_metadata() -> None:
    from unittest.mock import MagicMock

    from investwatch.storage.minio import SHA_META, MinioStore

    store = MinioStore("localhost:9", "a", "b", "bucket", False)
    store._ready = True
    client = MagicMock()
    store._client = client
    store.put_bytes("k", b"evidence", "text/plain")
    meta = client.put_object.call_args.kwargs["metadata"]
    assert meta == {SHA_META: hashlib.sha256(b"evidence").hexdigest()}
    client.stat_object.return_value = MagicMock(
        size=8, metadata={f"X-Amz-Meta-{SHA_META}": meta[SHA_META]}
    )
    assert store.describe("k") == (8, meta[SHA_META])
    client.get_object.assert_not_called()  # no download when the metadata has the hash
