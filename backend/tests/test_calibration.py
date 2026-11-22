from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from investwatch.calibration import best, build_report, histogram, point
from investwatch.db.session import session_scope
from investwatch.main import app
from investwatch.seed import golden_labels, seed_golden_labels


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_point_counts_and_scores() -> None:
    scored = [(0.9, 1), (0.7, 1), (0.6, 0), (0.2, 0), (0.1, 1)]
    p = point(scored, 0.65)
    assert (p.tp, p.fp, p.fn, p.tn) == (2, 0, 1, 2)
    assert p.precision == 1.0 and p.recall == pytest.approx(0.6667, abs=1e-4)
    assert p.f1 == pytest.approx(0.8) and p.f2 == pytest.approx(0.7143, abs=1e-4)
    # The threshold is inclusive: a score equal to it raises an alert.
    assert point(scored, 0.7).tp == 2


def test_report_recommends_thresholds() -> None:
    labelled = [(0.9, 1), (0.8, 1), (0.75, 0), (0.4, 1), (0.3, 0), (0.1, 0)]
    report = build_report("m2_risk_disclosure", labelled, [0.5, 0.95], 0.6, {"golden": 6})
    assert report.n_labels == 6 and report.n_positive == 3
    assert [p.threshold for p in report.points][:3] == [0.0, 0.01, 0.02]
    assert len(report.points) == 101
    assert report.recommended_f1 == 0.4
    assert report.recommended_f2 <= report.recommended_f1
    assert sum(b.count for b in report.histogram) == 8
    assert sum(b.positives for b in report.histogram) == 3
    assert report.labels_by_source == {"golden": 6} and report.min_labels == 20


def test_no_labels_keeps_current_threshold() -> None:
    report = build_report("m1_third_party_ad", [], [0.3], 0.55)
    assert report.n_labels == 0
    assert report.recommended_f1 == report.recommended_f2 == 0.55
    assert best(report.points, "f1", 0.55) == 0.55


def test_histogram_edges() -> None:
    bins = histogram([0.0, 0.049, 0.05, 1.0], [(1.0, 1)])
    assert len(bins) == 20
    assert bins[0].count == 2 and bins[1].count == 1 and bins[-1].count == 1
    assert bins[-1].positives == 1


def test_golden_labels_only_compliant_sources() -> None:
    from investwatch.config import get_settings

    rows = golden_labels(get_settings().data_dir / "golden")
    assert rows, "data/golden/predictions.jsonl missing: run `make eval`"
    methods = {r["provenance"]["method"] for r in rows}
    assert not methods & {"yt_dlp", "meta_ad_library_page", "tiktok_page"}
    assert {r["module"] for r in rows} == {
        "m1_third_party_ad",
        "m2_risk_disclosure",
        "m3_shadow_advisory",
    }


def test_calibration_api_from_labels(client: TestClient) -> None:
    empty = client.get("/api/calibration/m2_risk_disclosure").json()
    assert empty["labels_by_source"] == {"golden": 0, "analyst": 0}
    with session_scope() as s:
        loaded = seed_golden_labels(s)
    assert loaded > 50
    with session_scope() as s:
        assert seed_golden_labels(s) == loaded  # idempotent replace

    reports = {
        m: client.get(f"/api/calibration/{m}").json()
        for m in ("m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory")
    }
    for report in reports.values():
        assert report["n_labels"] == report["labels_by_source"]["golden"] > 0
        assert len(report["points"]) == 101 and len(report["histogram"]) == 20
    # Curves come from each module's own labels, not a shared fixture.
    curves = {m: [p["f1"] for p in r["points"]] for m, r in reports.items()}
    assert len({tuple(c) for c in curves.values()}) == 3

    golden_only = client.get(
        "/api/calibration/m2_risk_disclosure", params={"source": "golden"}
    ).json()
    assert "analyst" not in golden_only["labels_by_source"]


def test_status_change_feeds_calibration(client: TestClient) -> None:
    module = "m2_risk_disclosure"
    findings = client.get("/api/findings", params={"module": module}).json()["items"]
    fid = findings[0]["id"]
    before = client.get(f"/api/calibration/{module}").json()
    assert before["labels_by_source"]["analyst"] == 0

    client.patch(f"/api/findings/{fid}", json={"status": "confirmed"})
    after = client.get(f"/api/calibration/{module}").json()
    assert after["labels_by_source"]["analyst"] == 1
    assert after["n_labels"] == before["n_labels"] + 1
    assert after["n_positive"] == before["n_positive"] + 1
    assert after["points"][0]["tp"] == before["points"][0]["tp"] + 1

    client.patch(f"/api/findings/{fid}", json={"status": "dismissed"})
    dismissed = client.get(f"/api/calibration/{module}").json()
    assert dismissed["n_labels"] == before["n_labels"] + 1
    assert dismissed["n_positive"] == before["n_positive"]

    client.patch(f"/api/findings/{fid}", json={"status": "in_review"})
    reset = client.get(f"/api/calibration/{module}").json()
    assert reset["n_labels"] == before["n_labels"]
