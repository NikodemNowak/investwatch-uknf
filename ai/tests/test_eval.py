from __future__ import annotations

from pathlib import Path

import pytest

from investwatch_ai.config import Settings
from investwatch_ai.eval.__main__ import ci_subset, main
from investwatch_ai.eval.golden import GoldenItem, Provenance
from investwatch_ai.eval.metrics import Confusion, at_threshold, best_threshold, confusion, sweep
from investwatch_ai.eval.report import RunInfo, build_report
from investwatch_ai.eval.run import load_golden, predict, run

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "data" / "golden"
AI_COPY = REPO / "ai" / "src" / "investwatch_ai" / "eval" / "golden.py"
BACKEND = REPO / "backend" / "src" / "investwatch" / "golden" / "schemas.py"
needs_golden = pytest.mark.skipif(
    not (GOLDEN / "golden.jsonl").exists(), reason="data/golden not present (Docker build)"
)


@pytest.mark.skipif(not BACKEND.exists(), reason="backend/ not present")
def test_golden_schema_copy_matches_backend() -> None:
    backend = BACKEND.read_text().replace(
        "from investwatch.core.schemas import", "from ..schemas import"
    )
    assert AI_COPY.read_text() == backend, "sync ai/.../eval/golden.py with backend golden/schemas"


def test_confusion_and_f_scores() -> None:
    c = confusion([(True, True), (True, False), (False, True), (False, False), (True, True)])
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 1, 1, 1)
    assert c.precision == pytest.approx(2 / 3)
    assert c.recall == pytest.approx(2 / 3)
    assert c.f1 == pytest.approx(2 / 3)
    assert Confusion().f2 == 0.0
    # F2 favours recall: perfect recall with poor precision beats the reverse.
    assert Confusion(tp=4, fp=6).f2 > Confusion(tp=1, fn=3).f2


def test_sweep_and_best_threshold() -> None:
    scored = [(0.9, True), (0.7, True), (0.6, False), (0.2, False), (0.1, True)]
    curve = sweep(scored)
    assert len(curve) == 101 and curve[0][0] == 0.0 and curve[-1][0] == 1.0
    assert curve[0][1] == Confusion(tp=3, fp=2)
    assert at_threshold(scored, 0.65) == Confusion(tp=2, fn=1, tn=2)
    assert best_threshold(curve, 1.0) == 0.7
    assert best_threshold(curve, 2.0) == 0.1
    assert best_threshold(sweep([(0.3, False)]), 1.0, default=0.42) == 0.42


def test_headline_excludes_scraped_social() -> None:
    assert Provenance(collector="web", method="http_robots_respecting", compliant="yes").headline
    assert not Provenance(collector="youtube", method="yt_dlp", compliant="yes").headline
    assert not Provenance(collector="x", method="manual", compliant="under_review").headline


@needs_golden
def test_every_item_has_provenance_and_valid_split() -> None:
    items = load_golden(GOLDEN / "golden.jsonl")
    assert len(items) > 150
    assert {i.split for i in items} == {"train", "holdout"}
    by_group: dict[tuple[str, str], set[str]] = {}
    for item in items:
        by_group.setdefault((item.module, item.group), set()).add(item.split)
    assert all(len(s) == 1 for s in by_group.values()), "a leakage group spans both splits"


@needs_golden
def test_synthetic_pages_follow_their_construction() -> None:
    items = {i.id: i for i in load_golden(GOLDEN / "golden.jsonl")}
    settings = Settings()
    baseline = predict(GOLDEN, items["syn-m2-001"], settings)
    assert not baseline.predicted and baseline.rules["4"] == "pass"
    tiny = predict(GOLDEN, items["syn-m2-002"], settings)
    assert tiny.rules["4"] == "fail"


@needs_golden
def test_ci_subset_report(tmp_path: Path) -> None:
    items = ci_subset(load_golden(GOLDEN / "golden.jsonl"))
    assert 10 < len(items) < 80
    assert all(i.provenance.headline for i in items)
    preds = run(GOLDEN, items, Settings())
    assert all(0.0 <= p.score <= 1.0 for p in preds)
    report = build_report(items, preds, RunInfo("rules", "none", "now", "ci"))
    for module in ("m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory"):
        assert f"| {module} |" in report
    assert "Per-rule metrics" in report and "Timing" in report


@needs_golden
def test_cli_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "eval.md"
    preds = tmp_path / "p.jsonl"
    assert main(["--subset", "ci", "--out", str(out), "--predictions", str(preds)]) == 0
    assert out.read_text().startswith("# Golden-set evaluation")
    assert preds.read_text().count("\n") > 10


def test_excluded_items_are_skipped(tmp_path: Path) -> None:
    item = GoldenItem.model_validate(
        {
            "id": "x",
            "module": "m3_shadow_advisory",
            "label": 1,
            "origin": "synthetic",
            "provenance": {"collector": "synthetic", "method": "generator", "compliant": "yes"},
            "group": "g",
            "post": {
                "platform": "web",
                "collector": "synthetic",
                "external_id": "u",
                "url": "https://a.example/",
                "author": "a.example",
                "text": "Powiem Ci, co kupić.",
            },
            "labeler": "generator",
            "confidence": 1.0,
            "review": {"by": "t", "at": "now", "decision": "excluded"},
        }
    )
    assert run(tmp_path, [item], Settings()) == []


def test_bootstrap_ci_brackets_the_point_estimate_and_is_seeded() -> None:
    from investwatch_ai.eval.metrics import bootstrap_ci, confusion

    pairs = [(True, True)] * 6 + [(True, False)] * 2 + [(False, False)] * 8 + [(False, True)]
    lo, hi = bootstrap_ci(pairs, lambda c: c.f1)
    assert lo <= confusion(pairs).f1 <= hi
    assert (lo, hi) == bootstrap_ci(pairs, lambda c: c.f1)
    assert bootstrap_ci([], lambda c: c.f1) == (0.0, 0.0)


def test_comparison_block_replaces_an_older_one() -> None:
    from investwatch_ai.eval.compare import END, START, insert

    report = "# R\n\n## Headline\nx\n\n## Breakdowns\ny\n"
    first = insert(report, f"{START}\nA\n{END}\n")
    assert "A" in first and first.index("A") < first.index("## Breakdowns")
    second = insert(first, f"{START}\nB\n{END}\n")
    assert "B" in second and "\nA\n" not in second and second.count(START) == 1
