from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from investwatch.main import app


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in body["items"]}


def test_findings_accept_several_values_per_filter(client: TestClient) -> None:
    def total(params: list[tuple[str, str]]) -> int:
        return int(client.get("/api/findings", params=params).json()["total"])

    open_ = total([("status", "new"), ("status", "in_review")])
    assert open_ == total([("status", "new")]) + total([("status", "in_review")]) == 7
    both = total([("platform", "youtube"), ("platform", "facebook")])
    assert both == total([("platform", "youtube")]) + total([("platform", "facebook")])
    assert total([("risk_level", "high"), ("risk_level", "low")]) == 9
    assert client.get("/api/findings", params={"status": "bogus"}).status_code == 422


def test_entities_merge_modules_per_firm_and_advertiser(client: TestClient) -> None:
    body = client.get("/api/entities").json()
    assert body["findings"] == 12 and body["truncated"] is False
    entities = _by_name(body)
    kyrenia = entities["Kyrenia Prime Ltd"]
    assert kyrenia["kind"] == "firm" and kyrenia["key"].startswith("firm:")
    assert kyrenia["modules"] == {
        "m1_third_party_ad": 2,
        "m2_risk_disclosure": 1,
        "m3_shadow_advisory": 0,
    }
    assert kyrenia["highest_risk"] == "high" and kyrenia["total"] == 3
    assert kyrenia["knf_register"] in {"knf", "fictional"}
    kasia = entities["@InwestujZKasia"]
    assert kasia["kind"] == "advertiser" and kasia["knf_register"] == "absent"
    assert kasia["modules"]["m1_third_party_ad"] == 1
    assert kasia["modules"]["m3_shadow_advisory"] == 1
    assert kasia["confirmed"] == 1 and kasia["open"] == 1
    assert kasia["platforms"] == ["youtube"]
    risks = [e["highest_risk"] for e in body["items"]]
    rank = {"high": 3, "medium": 2, "low": 1}
    assert risks == sorted(risks, key=rank.__getitem__, reverse=True)


def test_entities_respect_filters_and_search(client: TestClient) -> None:
    m3 = client.get("/api/entities", params={"module": "m3_shadow_advisory"}).json()
    assert all(e["kind"] == "advertiser" for e in m3["items"]) and m3["findings"] == 4
    found = client.get("/api/entities", params={"q": "kyrenia"}).json()
    assert [e["name"] for e in found["items"]] == ["Kyrenia Prime Ltd"]
    day = client.get("/api/entities", params={"from": "2026-11-21", "to": "2026-11-21"}).json()
    assert day["findings"] == 1 and day["total"] == 1
    yt_open = client.get(
        "/api/entities",
        params=[("platform", "youtube"), ("status", "new"), ("status", "in_review")],
    ).json()
    assert yt_open["findings"] == 3


def test_entity_detail_drills_down_to_findings(client: TestClient) -> None:
    key = _by_name(client.get("/api/entities").json())["@InwestujZKasia"]["key"]
    assert key == "name:inwestujzkasia"
    detail = client.get(f"/api/entities/{key}").json()
    assert detail["name"] == "@InwestujZKasia" and len(detail["findings"]) == 2
    dates = [f["created_at"] for f in detail["findings"]]
    assert dates == sorted(dates, reverse=True)
    assert {f["module"] for f in detail["findings"]} == {
        "m1_third_party_ad",
        "m3_shadow_advisory",
    }
    assert client.get("/api/entities/name:nobody").status_code == 404
