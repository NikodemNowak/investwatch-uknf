from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from investwatch_ai.rules import RuleContext, evaluate
from investwatch_ai.rules.render_checks import (
    contrast_ratio,
    dominant_font_px,
    exposure,
    font_size,
    hidden_low,
    one_click,
    past_performance_dominance,
    responsive,
)
from investwatch_ai.schemas import RenderSnapshot, RuleResult, TextBlock, Viewport

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"

GAINS = "Zarabiaj średnio 38% rocznie z naszym programem."
BODY = "Nasz zespół analizuje rynki każdego dnia i publikuje komentarze dla klientów."
RISK = (
    "Kontrakty CFD są złożonymi instrumentami i wiążą się z wysokim ryzykiem szybkiej utraty "
    "środków pieniężnych z powodu dźwigni finansowej."
)
PAST = "+142% w 2025 roku"


def blk(text: str, **kw: Any) -> TextBlock:
    """A visible 16 px black-on-white block unless overridden."""
    base: dict[str, Any] = {
        "text": text,
        "bbox": (24.0, 200.0, 800.0, 24.0),
        "font_px": 16.0,
        "font_weight": 400,
        "color": "#1a1a1a",
        "background": "#ffffff",
        "opacity": 1.0,
        "visible": True,
        "occluded": False,
        "clipped": False,
        "in_footer": False,
        "in_collapsed": False,
        "y_ratio": 0.1,
        "tag_path": "html>body>main>p",
    }
    base.update(kw)
    return TextBlock.model_validate(base)


def snap(
    blocks: list[TextBlock],
    per_viewport: dict[Viewport, list[TextBlock]] | None = None,
    height: float = 2000.0,
) -> RenderSnapshot:
    viewports: dict[Viewport, list[TextBlock]] = {
        "desktop": blocks,
        "tablet": blocks,
        "phone": blocks,
    }
    viewports.update(per_viewport or {})
    return RenderSnapshot(viewports=viewports, page_height=dict.fromkeys(viewports, height))


def page(*, risk: TextBlock | None = None, extra: list[TextBlock] | None = None) -> list[TextBlock]:
    blocks = [
        blk(GAINS, font_px=28.0, bbox=(24.0, 120.0, 800.0, 36.0), y_ratio=0.06),
        blk(BODY, bbox=(24.0, 300.0, 800.0, 48.0), y_ratio=0.15),
        blk(BODY + " Otwórz konto w 3 minuty.", bbox=(24.0, 360.0, 800.0, 48.0), y_ratio=0.18),
    ]
    if risk is not None:
        blocks.append(risk)
    return blocks + (extra or [])


COMPLIANT_RISK = blk(RISK, bbox=(24.0, 170.0, 800.0, 48.0), y_ratio=0.085, font_weight=600)


# Pure helpers


def test_contrast_ratio_matches_wcag() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#c4c4c4", "#ffffff") == pytest.approx(1.74, abs=0.01)
    assert contrast_ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)


def test_dominant_font_is_length_weighted_median() -> None:
    blocks = [blk("x" * 10, font_px=48.0), blk("y" * 200, font_px=16.0), blk("z" * 5, font_px=9.0)]
    assert dominant_font_px(blocks) == 16.0


# Rule 4


def test_rule4_fails_for_8px_risk_vs_16px_body() -> None:
    risk = blk(RISK, font_px=8.0, in_footer=True, y_ratio=0.95, bbox=(24.0, 1900.0, 800.0, 20.0))
    out = font_size(snap(page(risk=risk)))
    assert out.status == "fail"
    ev = out.evidence[0]
    assert ev.measurements["ratio"] == 0.5
    assert ev.measurements["risk_font_px"] == 8.0
    assert ev.measurements["dominant_font_px"] == 16.0
    assert ev.viewport == "desktop"
    assert ev.bbox == (24.0, 1900.0, 800.0, 20.0)


def test_rule4_passes_with_equal_font() -> None:
    out = font_size(snap(page(risk=COMPLIANT_RISK)))
    assert out.status == "pass"
    assert out.evidence[0].measurements["ratio"] == 1.0


def test_rule4_tolerates_small_difference() -> None:
    out = font_size(snap(page(risk=blk(RISK, font_px=15.4))))
    assert out.status == "pass"


def test_rule4_unknown_when_render_has_no_risk_block() -> None:
    assert font_size(snap(page())).status == "unknown"


# Rule 5


def test_rule5_fails_on_low_contrast() -> None:
    risk = blk(RISK, color="#c4c4c4", background="#ffffff")
    out = exposure(snap(page(risk=risk)))
    assert out.status == "fail"
    m = out.evidence[0].measurements
    assert m["contrast"] == pytest.approx(1.74, abs=0.01)
    assert m["color"] == "#c4c4c4" and m["background"] == "#ffffff"
    assert out.evidence[0].bbox is not None


def test_rule5_rounds_contrast_down_like_the_dashboard() -> None:
    # #d6d6d6 on white is 1.453:1; the dashboard shows "1,4:1", so must the rule text.
    risk = blk(RISK, color="#d6d6d6", background="#ffffff")
    out = exposure(snap(page(risk=risk)))
    assert "kontrast 1,4:1" in out.explanation


def test_rule5_fails_when_occluded_or_faded() -> None:
    assert exposure(snap(page(risk=blk(RISK, occluded=True)))).status == "fail"
    faded = exposure(snap(page(risk=blk(RISK, opacity=0.4))))
    assert faded.status == "fail"
    assert faded.evidence[0].measurements["opacity"] == 0.4


def test_rule5_passes_for_readable_block() -> None:
    out = exposure(snap(page(risk=COMPLIANT_RISK)))
    assert out.status == "pass"
    assert out.evidence[0].measurements["contrast"] > 4.5


# Rule 6


def test_rule6_fails_when_risk_only_in_footer_and_gains_on_first_screen() -> None:
    risk = blk(RISK, in_footer=True, y_ratio=0.96, bbox=(24.0, 1920.0, 800.0, 24.0))
    out = hidden_low(snap(page(risk=risk)))
    assert out.status == "fail"
    assert out.evidence[0].measurements["y_ratio"] == 0.96


def test_rule6_passes_when_risk_next_to_gains() -> None:
    assert hidden_low(snap(page(risk=COMPLIANT_RISK))).status == "pass"


def test_rule6_low_on_page_ignored_when_page_fits_first_screen() -> None:
    risk = blk(RISK, y_ratio=0.9, bbox=(24.0, 600.0, 800.0, 24.0))
    assert hidden_low(snap(page(risk=risk), height=700.0)).status == "pass"


# Rule 7


def test_rule7_fails_for_collapsed_details() -> None:
    summary = blk(
        "Informacje prawne",
        font_px=10.0,
        in_footer=True,
        tag_path="html>body>footer>details>summary",
        bbox=(24.0, 1900.0, 120.0, 14.0),
        y_ratio=0.95,
    )
    risk = blk(
        RISK,
        visible=False,
        in_collapsed=True,
        in_footer=True,
        tag_path="html>body>footer>details>p",
        bbox=(24.0, 1900.0, 120.0, 14.0),
        y_ratio=0.95,
    )
    out = one_click(snap(page(risk=risk, extra=[summary])))
    assert out.status == "fail"
    ev = out.evidence[0]
    assert ev.measurements["in_collapsed"] == "true"
    assert ev.bbox == (24.0, 1900.0, 120.0, 14.0)


def test_rule7_fails_when_collapsed_only_on_phone() -> None:
    hidden = blk(RISK, visible=False, in_collapsed=True, tag_path="html>body>footer>details>p")
    summary = blk("Pokaż ostrzeżenie o ryzyku", tag_path="html>body>footer>details>summary")
    out = one_click(
        snap(page(risk=COMPLIANT_RISK), per_viewport={"phone": page(risk=hidden, extra=[summary])})
    )
    assert out.status == "fail"
    assert {e.viewport for e in out.evidence} == {"phone"}
    assert out.evidence[-1].quote == "Pokaż ostrzeżenie o ryzyku"


def test_rule7_fails_when_only_a_link() -> None:
    link = blk("Przeczytaj ostrzeżenie o ryzyku", tag_path="html>body>main>p>a")
    out = one_click(snap(page(extra=[link])))
    assert out.status == "fail"
    assert out.evidence[0].quote == "Przeczytaj ostrzeżenie o ryzyku"


def test_rule7_passes_for_visible_risk() -> None:
    assert one_click(snap(page(risk=COMPLIANT_RISK))).status == "pass"


def test_rule7_na_without_any_risk_trace() -> None:
    assert one_click(snap(page())).status == "na"


# Rule 8


def test_rule8_fails_when_clipped_on_phone() -> None:
    phone_risk = blk(RISK, clipped=True, bbox=(16.0, 400.0, 358.0, 20.0))
    out = responsive(snap(page(risk=COMPLIANT_RISK), per_viewport={"phone": page(risk=phone_risk)}))
    assert out.status == "fail"
    assert [e.viewport for e in out.evidence] == ["phone"]
    assert out.evidence[0].measurements["clipped"] == "true"


def test_rule8_names_only_the_failing_devices() -> None:
    phone_risk = blk(RISK, clipped=True, bbox=(16.0, 400.0, 358.0, 20.0))
    out = responsive(snap(page(risk=COMPLIANT_RISK), per_viewport={"phone": page(risk=phone_risk)}))
    assert out.status == "fail"
    assert {e.measurements["failed_viewports"] for e in out.evidence} == {"phone"}
    assert "telefon" in out.explanation and "komputer" not in out.explanation


def test_rule8_fails_below_12px_and_when_ratio_shrinks() -> None:
    small = page(risk=blk(RISK, font_px=11.0))
    assert responsive(snap(page(risk=COMPLIANT_RISK), per_viewport={"phone": small})).status == (
        "fail"
    )
    # 12 px risk next to 16 px body on the tablet: absolute size fine, ratio 0.75 < 1.0.
    shrunk = page(risk=blk(RISK, font_px=12.0))
    out = responsive(snap(page(risk=COMPLIANT_RISK), per_viewport={"tablet": shrunk}))
    assert out.status == "fail"
    assert out.evidence[0].viewport == "tablet"
    assert out.evidence[0].measurements["ratio"] == 0.75


def test_rule8_passes_in_all_viewports() -> None:
    out = responsive(snap(page(risk=COMPLIANT_RISK)))
    assert out.status == "pass"
    assert {e.viewport for e in out.evidence} == {"desktop", "tablet", "phone"}


# Rule 13


def test_rule13_fails_when_past_performance_dominates() -> None:
    hero = blk(PAST, font_px=72.0, bbox=(24.0, 80.0, 800.0, 90.0), y_ratio=0.04)
    out = past_performance_dominance(snap([hero, *page(risk=COMPLIANT_RISK)]))
    assert out.status == "fail"
    assert out.evidence[0].measurements["font_px"] == 72.0


def test_rule13_passes_when_past_performance_is_secondary() -> None:
    small = blk("W 2025 r. fundusz osiągnął stopę zwrotu 7,2%.", y_ratio=0.3)
    out = past_performance_dominance(snap([*page(risk=COMPLIANT_RISK), small]))
    assert out.status == "pass"


# Registry wiring


def _rules(text: str, render: RenderSnapshot | None) -> dict[str, RuleResult]:
    return {r.rule_id: r for r in evaluate(RuleContext.build(text, render=render))}


def test_compliant_page_passes_all_render_rules() -> None:
    blocks = page(risk=COMPLIANT_RISK)
    text = "\n".join(b.text for b in blocks)
    res = _rules(text, snap(blocks))
    for rid in ("4", "5", "6", "7", "8"):
        assert res[rid].status == "pass", (rid, res[rid].explanation)
        assert res[rid].evidence and all(e.bbox and e.viewport for e in res[rid].evidence)


def test_render_rules_na_without_risk_or_gains() -> None:
    blocks = [blk(BODY)]
    res = _rules(BODY, snap(blocks))
    for rid in ("4", "5", "6", "7", "8", "13"):
        assert res[rid].status == "na", rid


def test_fixture_snapshot_fails_rules_4_to_8() -> None:
    data = json.loads((FIXTURES / "render_snapshot.json").read_text(encoding="utf-8"))
    render = RenderSnapshot.model_validate(data)
    text = "\n".join(b.text for b in render.viewports["desktop"])
    res = _rules(text, render)
    assert res["4"].status == "fail"
    assert res["4"].evidence[0].measurements["risk_font_px"] == 9.0
    assert res["5"].status == "fail"
    assert res["8"].status == "fail"
