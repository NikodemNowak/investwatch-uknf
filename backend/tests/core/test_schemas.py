from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from investwatch.core.schemas import (
    Alert,
    CalibrationReport,
    Evidence,
    Finding,
    FirmMatch,
    Post,
    RegisteredFirm,
    RenderSnapshot,
    RuleResult,
    TextBlock,
    TrendSeries,
)

FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures"
M2_RULE_IDS = {str(i) for i in range(1, 19) if i != 12} | {"12a", "12b"}


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _posts() -> list[Post]:
    return TypeAdapter(list[Post]).validate_python(_load("posts.json"))


def _findings() -> list[Finding]:
    return TypeAdapter(list[Finding]).validate_python(_load("findings.json"))


def _firms() -> list[RegisteredFirm]:
    return TypeAdapter(list[RegisteredFirm]).validate_python(_load("firms.json"))


def _assert_round_trip(model: BaseModel) -> None:
    restored = type(model).model_validate_json(model.model_dump_json())
    assert restored == model


def _text_block() -> TextBlock:
    return TextBlock(
        text="Inwestowanie wiąże się z ryzykiem.",
        bbox=(16.0, 1200.0, 400.0, 12.0),
        font_px=9.0,
        font_weight=400,
        color="#b8b8b8",
        background="#ffffff",
        opacity=1.0,
        visible=True,
        occluded=False,
        clipped=False,
        in_footer=True,
        in_collapsed=False,
        y_ratio=0.97,
        tag_path="html>body>footer>p",
    )


def _evidence() -> Evidence:
    return Evidence(
        quote="Inwestowanie wiąże się z ryzykiem.",
        viewport="desktop",
        bbox=(16.0, 1200.0, 400.0, 12.0),
        measurements={"risk_font_px": 9, "dominant_font_px": 16, "ratio": 0.56},
    )


def _rule_result() -> RuleResult:
    return RuleResult(
        rule_id="4",
        name="Rozmiar czcionki ryzyka",
        status="fail",
        confidence=0.9,
        check_type="render",
        weight=0.6,
        explanation="Czcionka ostrzeżenia jest mniejsza niż dominująca.",
        legal_basis="art. 44 ust. 2 lit. c rozporządzenia del. 2017/565",
        evidence=[_evidence()],
    )


def test_text_block_round_trip() -> None:
    _assert_round_trip(_text_block())


def test_evidence_round_trip() -> None:
    _assert_round_trip(_evidence())


def test_rule_result_round_trip() -> None:
    _assert_round_trip(_rule_result())


def test_post_round_trip() -> None:
    for post in _posts():
        _assert_round_trip(post)


def test_registered_firm_round_trip() -> None:
    for firm in _firms():
        _assert_round_trip(firm)


def test_firm_match_round_trip() -> None:
    match = FirmMatch(
        firm=_firms()[0], confidence=1.0, method="domain", matched_text="x.example", on="author"
    )
    _assert_round_trip(match)


def test_finding_round_trip() -> None:
    for finding in _findings():
        _assert_round_trip(finding)


def test_alert_round_trip() -> None:
    finding = _findings()[0]
    post = next(p for p in _posts() if p.id == finding.post_id)
    _assert_round_trip(Alert(finding=finding, post=post))


def test_render_snapshot_round_trip() -> None:
    snapshot = RenderSnapshot(
        viewports={"desktop": [_text_block()]}, page_height={"desktop": 1240.0}
    )
    _assert_round_trip(snapshot)


def test_unknown_fields_are_rejected() -> None:
    data = _load("firms.json")[0] | {"unexpected": 1}
    with pytest.raises(ValidationError):
        RegisteredFirm.model_validate(data)


def test_scores_are_bounded() -> None:
    data = _load("findings.json")[0] | {"score": 1.5}
    with pytest.raises(ValidationError):
        Finding.model_validate(data)


def test_posts_fixture() -> None:
    posts = _posts()
    assert len(posts) == 10
    assert {p.platform for p in posts} >= {"web", "youtube", "facebook"}
    assert sum(p.fetch_status == "blocked" for p in posts) == 1
    assert any(p.text == "" and p.fetch_status != "blocked" for p in posts)
    assert len({p.id for p in posts}) == 10


def test_firms_fixture() -> None:
    firms = _firms()
    assert len(firms) == 8
    kinds = [f.kind for f in firms]
    assert all(kinds.count(k) == 2 for k in set(kinds))
    assert len(set(kinds)) == 4


def test_findings_fixture() -> None:
    findings = _findings()
    post_ids = {p.id for p in _posts()}
    assert len(findings) == 12
    for module in ("m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory"):
        assert sum(f.module == module for f in findings) == 4
    for finding in findings:
        assert finding.post_id in post_ids
        if finding.module == "m2_risk_disclosure":
            assert {r.rule_id for r in finding.rules} == M2_RULE_IDS
            assert finding.firm is not None
    m2_bboxes = [
        e.bbox
        for f in findings
        if f.module == "m2_risk_disclosure"
        for r in f.rules
        for e in r.evidence
        if e.bbox is not None
    ]
    assert m2_bboxes


def test_render_snapshot_fixture() -> None:
    snapshot = RenderSnapshot.model_validate(_load("render_snapshot.json"))
    assert set(snapshot.viewports) == {"desktop", "tablet", "phone"}
    _assert_round_trip(snapshot)
    desktop = snapshot.viewports["desktop"]
    assert min(b.font_px for b in desktop) == 9.0
    assert any(b.font_px == 16.0 for b in desktop)


def test_calibration_fixture() -> None:
    report = CalibrationReport.model_validate(_load("calibration.json"))
    _assert_round_trip(report)
    assert len(report.points) == 101
    assert report.points[0].threshold == 0.0
    assert report.points[-1].threshold == 1.0


def test_trend_fixture() -> None:
    trend = TrendSeries.model_validate(_load("trend.json"))
    _assert_round_trip(trend)
    assert trend.points
    assert all(p.total == p.high + p.medium + p.low for p in trend.points)


def test_datetimes_are_timezone_aware() -> None:
    for post in _posts():
        assert post.first_seen_at.tzinfo is not None
    for finding in _findings():
        assert finding.created_at.tzinfo is not None
