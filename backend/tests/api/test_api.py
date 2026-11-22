from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from investwatch.collectors.base import MemoryRateLimiter, PoliteFetcher
from investwatch.collectors.web import WebCollector
from investwatch.config import get_settings
from investwatch.main import app
from investwatch.realtime.emitter import MemoryEmitter


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_list_findings_with_filters(client: TestClient) -> None:
    body = client.get("/api/findings").json()
    assert body["total"] == 12 and len(body["items"]) == 12
    assert (body["page"], body["page_size"]) == (1, 50)
    page = client.get("/api/findings", params={"page": 2, "page_size": 5}).json()
    assert len(page["items"]) == 5 and page["page"] == 2
    day = client.get("/api/findings", params={"from": "2026-11-21", "to": "2026-11-21"}).json()
    assert day["total"] == 1  # the fixture finding created 2026-11-21T07:10
    assert {"post", "rules", "firm", "score"} <= set(body["items"][0])
    r = client.get(
        "/api/findings",
        params={
            "module": "m3_shadow_advisory",
            "status": "confirmed",
            "from": "2026-11-01T00:00:00Z",
        },
    )
    assert r.status_code == 200
    assert [f["module"] for f in r.json()["items"]] == ["m3_shadow_advisory"]
    assert client.get("/api/findings", params={"risk_level": "bogus"}).status_code == 422


def test_get_and_patch_finding(client: TestClient) -> None:
    fid = client.get("/api/findings").json()["items"][0]["id"]
    assert client.get(f"/api/findings/{fid}").json()["id"] == fid
    r = client.patch(f"/api/findings/{fid}", json={"status": "dismissed"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert client.patch(f"/api/findings/{fid}", json={"status": "nope"}).status_code == 422
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/findings/{missing}").status_code == 404


def test_stats(client: TestClient) -> None:
    trend = client.get("/api/stats/trend", params={"from": "2026-11-14", "to": "2026-11-21"}).json()
    assert trend["bucket"] == "day" and sum(p["total"] for p in trend["points"]) == 12
    assert (
        client.get(
            "/api/stats/trend", params={"from": "2026-11-21", "to": "2026-11-01"}
        ).status_code
        == 422
    )
    auto = client.get("/api/stats/trend", params={"bucket": "auto"}).json()
    assert auto["bucket"] in {"hour", "day"}
    assert client.get("/api/stats/trend", params={"bucket": "hour"}).status_code == 422
    summary = client.get("/api/stats/summary").json()
    assert summary["findings"] == 12


def test_thresholds_and_calibration(client: TestClient) -> None:
    assert client.get("/api/settings/thresholds").json() == {
        "m1_third_party_ad": 0.2,
        "m2_risk_disclosure": 0.3,
        "m3_shadow_advisory": 0.12,
    }
    new = {"m1_third_party_ad": 0.5, "m2_risk_disclosure": 0.6, "m3_shadow_advisory": 0.8}
    assert client.put("/api/settings/thresholds", json=new).json() == new
    report = client.get("/api/calibration/m3_shadow_advisory").json()
    assert report["module"] == "m3_shadow_advisory" and report["current_threshold"] == 0.8
    assert len(report["points"]) == 101
    bad = {**new, "m1_third_party_ad": 2}
    assert client.put("/api/settings/thresholds", json=bad).status_code == 422


def test_sources_crud_and_run(client: TestClient) -> None:
    from investwatch.seed import DEMO_SOURCES

    sources = client.get("/api/sources").json()
    assert len(sources) == len(DEMO_SOURCES)
    sample = next(s for s in sources if s["collector"] == "sample")
    r = client.post(f"/api/sources/{sample['id']}/run")
    assert r.status_code == 202
    runs = client.get(f"/api/sources/{sample['id']}/runs").json()
    assert runs[0]["status"] == "ok" and runs[0]["items_seen"] == 10
    listed = next(s for s in client.get("/api/sources").json() if s["id"] == sample["id"])
    assert listed["last_run_status"] == "ok" and listed["last_run_items"] == 10
    assert listed["platform"] == "sample" and listed["schedule"] == listed["cron"]

    created = client.post(
        "/api/sources",
        json={"name": "x", "collector": "web", "target": "http://e.example", "cron": "*/5 * * * *"},
    )
    assert created.status_code == 201
    sid = created.json()["id"]
    patched = client.patch(
        f"/api/sources/{sid}", json={"enabled": False, "cron": "0 * * * *"}
    ).json()
    assert patched["enabled"] is False and patched["next_run_at"]
    assert client.patch(f"/api/sources/{sid}", json={"cron": "bad cron"}).status_code == 422
    assert (
        client.post(
            "/api/sources", json={"name": "x", "collector": "nope", "target": ""}
        ).status_code
        == 422
    )


def test_check_text_end_to_end(client: TestClient, events: MemoryEmitter) -> None:
    text = "Gwarantujemy zysk 40% rocznie! Zarobisz minimum 3% miesięcznie."
    r = client.post("/api/check", json={"text": text})
    assert r.status_code == 202
    job = client.get(f"/api/check/{r.json()['job_id']}").json()
    assert job["state"] == "done" and job["finding_ids"]
    alerts = [data for name, data in events.events if name == "alert"]
    assert alerts and alerts[-1]["finding"]["module"] == "m2_risk_disclosure"
    stages = [d["stage"] for n, d in events.events if n == "job"]
    assert stages == ["queued", "fetched", "analyzed"]


def test_check_url_end_to_end(
    client: TestClient,
    events: MemoryEmitter,
    demo_html: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=demo_html["hidden-risk.html"])

    fetcher = PoliteFetcher(get_settings(), MemoryRateLimiter(0), httpx.MockTransport(handler))
    monkeypatch.setattr(
        "investwatch.jobs.tasks.WebCollector",
        lambda name: WebCollector(fetcher, name=name, render=False),
    )
    r = client.post("/api/check", json={"url": "http://demo-sites/hidden-risk.html"})
    assert r.status_code == 202
    job = client.get(f"/api/check/{r.json()['job_id']}").json()
    assert job["state"] == "done"
    finding = client.get(f"/api/findings/{job['finding_ids'][0]}").json()
    assert finding["post"]["collector"] == "manual"
    assert finding["post"]["html_key"].startswith("raw/")
    assert any(n == "alert" and d["finding"]["risk_level"] == "high" for n, d in events.events)
    html = client.get(f"/api/objects/{finding['post']['html_key']}")
    assert html.status_code == 200 and "Turbo Zysk" in html.text


def test_check_rejects_internal_urls(client: TestClient) -> None:
    assert client.post("/api/check", json={"url": "http://127.0.0.1:5432/"}).status_code == 422
    assert client.post("/api/check", json={}).status_code == 422
    assert (
        client.post("/api/check", json={"url": "http://a.example", "text": "x"}).status_code == 422
    )


def test_duplicate_text_is_not_reanalysed(client: TestClient, events: MemoryEmitter) -> None:
    from investwatch.collectors.sample import load_posts

    text = load_posts()[0].text
    job = client.post("/api/check", json={"text": text}).json()
    assert client.get(f"/api/check/{job['job_id']}").json()["finding_ids"] == []
    last = [d for n, d in events.events if n == "job"][-1]
    assert last["stage"] == "analyzed" and last["duplicate_of"]


def test_firms_and_objects(client: TestClient) -> None:
    page = client.get("/api/firms").json()
    assert page["total"] > 700 and len(page["items"]) == 50
    snap = client.get("/api/objects/render/a0000000-0000-4000-8000-000000000003.json")
    assert snap.status_code == 200 and "viewports" in snap.json()
    assert client.get("/api/objects/../etc/passwd").status_code == 404


def test_post_artefacts(client: TestClient) -> None:
    post3 = "a0000000-0000-4000-8000-000000000003"
    assert client.get(f"/api/posts/{post3}").json()["id"] == post3
    render = client.get(f"/api/posts/{post3}/render")
    assert render.status_code == 200 and set(render.json()["viewports"]) == {
        "desktop",
        "tablet",
        "phone",
    }
    post1 = "a0000000-0000-4000-8000-000000000001"
    assert client.get(f"/api/posts/{post1}/render").status_code == 404
    shot = client.get(f"/api/posts/{post3}/screenshots/phone")
    assert shot.status_code == 200 and shot.content.startswith(b"\x89PNG")
    assert client.get(f"/api/posts/{post1}/screenshots/desktop").status_code == 404
    assert client.get(f"/api/posts/{post3}/screenshots/watch").status_code == 422


def test_findings_accept_datetimes(client: TestClient) -> None:
    r = client.get("/api/findings", params={"from": "2026-11-21T07:00:00Z"}).json()
    assert r["total"] == 1


def test_reports_csv_and_json(client: TestClient) -> None:
    r = client.get("/api/reports/m1.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Firma inwestycyjna,") and len(lines) == 1 + 4
    semi = client.get("/api/reports/m1_third_party_ad.csv", params={"sep": ";"})
    assert semi.content.decode("utf-8-sig").startswith("Firma inwestycyjna;")

    body = client.get("/api/reports/m3.json", params={"status": "confirmed"}).json()
    assert body["module"] == "m3_shadow_advisory" and body["count"] == 1
    assert body["truncated"] is False
    assert body["items"][0]["art76_signals"][0].startswith("76a")
    m2 = client.get("/api/reports/m2.json", params={"min_score": 0.9, "sort": "score"}).json()
    assert [i["score"] for i in m2["items"]] == [0.999, 0.998]
    assert m2["items"][0]["violated_rules"]
    capped = client.get("/api/reports/m2.json", params={"limit": 1}).json()
    assert capped["count"] == 1 and capped["truncated"] is True

    assert client.get("/api/reports/m9.csv").status_code == 404
    assert client.get("/api/reports/m1.csv", params={"sep": "|"}).status_code == 422
