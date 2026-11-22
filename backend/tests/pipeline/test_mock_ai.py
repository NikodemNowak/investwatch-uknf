from __future__ import annotations

from investwatch.collectors.html_text import html_to_text
from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import Post
from investwatch.pipeline.dedup import to_post
from investwatch.pipeline.mock_ai import mock_analyze


def _post(text: str) -> Post:
    item = CollectedItem(
        platform="web", collector="manual", external_id="x", url="http://x/", author="x", text=text
    )
    return to_post(item)


def test_hidden_risk_page_is_high_risk(demo_html: dict[str, str]) -> None:
    post = _post(html_to_text(demo_html["hidden-risk.html"]))
    findings = {f.module: f for f in mock_analyze(post, []).findings}
    m2 = findings["m2_risk_disclosure"]
    assert m2.risk_level == "high"
    assert {r.rule_id for r in m2.rules if r.status == "fail"} >= {"3", "15"}
    assert m2.post_id == post.id and not m2.used_llm


def test_compliant_page_is_low_risk(demo_html: dict[str, str]) -> None:
    post = _post(html_to_text(demo_html["ok.html"]))
    findings = mock_analyze(post, []).findings
    assert all(f.risk_level == "low" for f in findings)


def test_advisory_post_hits_m3() -> None:
    text = "Konsultacje 1:1 – dobiorę ETF-y pod Twoją sytuację. Kupuj akcje CD Projekt teraz!"
    modules = {f.module for f in mock_analyze(_post(text), []).findings}
    assert "m3_shadow_advisory" in modules


def test_neutral_text_has_no_findings() -> None:
    assert mock_analyze(_post("Dzisiaj pada deszcz."), []).findings == []
