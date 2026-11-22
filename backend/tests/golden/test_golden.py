from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from investwatch.golden import build, label, real, synth
from investwatch.golden.schemas import GoldenItem

GOLDEN = Path(__file__).resolve().parents[3] / "data" / "golden"


def _item(item_id: str, group: str, module: str = "m3_shadow_advisory") -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "id": item_id,
            "module": module,
            "label": 1,
            "origin": "real",
            "provenance": {
                "collector": "web",
                "method": "http_robots_respecting",
                "compliant": "yes",
            },
            "group": group,
            "post": {
                "platform": "web",
                "collector": "web",
                "external_id": item_id,
                "url": f"https://{group}/",
                "author": group,
                "text": "x",
            },
            "labeler": "agent",
            "confidence": 0.7,
        }
    )


def test_rule_labels_follow_construction() -> None:
    tiny = synth.rule_labels(synth.PageSpec("sowa", "etf", frozenset({"tiny_font"})))
    assert tiny["4"] == "fail" and tiny["8"] == "fail" and tiny["5"] == "pass"
    clean = synth.rule_labels(synth.PageSpec("sowa", "etf", frozenset()))
    assert "fail" not in clean.values()
    no_risk = synth.rule_labels(synth.PageSpec("sowa", "etf", frozenset({"no_risk"})))
    assert no_risk["3"] == "fail" and no_risk["4"] == "na"


def test_parse_rules() -> None:
    assert synth.parse_rules("2=fail 76a=pass") == {"2": "fail", "76a": "pass"}
    with pytest.raises(ValueError):
        synth.parse_rules("2=maybe")


def test_split_keeps_groups_together_and_is_deterministic() -> None:
    items = [_item(f"i{i}", f"g{i % 7}.example") for i in range(40)]
    first = build.assign_splits(items)
    assert [i.split for i in first] == [i.split for i in build.assign_splits(items)]
    groups: dict[str, set[str]] = {}
    for item in first:
        groups.setdefault(item.group, set()).add(item.split)
    assert all(len(s) == 1 for s in groups.values())
    held = sum(i.split == "holdout" for i in first) / len(first)
    assert 0.2 <= held <= 0.6


def test_review_survives_rebuild() -> None:
    old = label.apply_decision(_item("a", "g.example"), "changed", "tester", new_label=0)
    rebuilt = build.keep_reviews([_item("a", "g.example"), _item("b", "h.example")], [old])
    assert rebuilt[0].label == 0 and rebuilt[0].review is not None
    assert rebuilt[0].review.previous_label == 1 and rebuilt[1].review is None


def test_agent_review_is_not_recorded_as_human() -> None:
    by = "agent-consensus:3xsonnet+opus"
    item = label.apply_decision(_item("a", "g.example"), "changed", by, 0, labeler="agent")
    assert item.labeler == "agent" and item.review is not None and item.review.by == by
    item = label.apply_decision(item, "changed", by, 1, comment="why", labeler="agent")
    rebuilt = build.keep_reviews([_item("a", "g.example")], [item])
    assert rebuilt[0].labeler == "agent" and rebuilt[0].label == 1
    assert "review: why" in rebuilt[0].note


def test_label_csv_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "golden.jsonl"
    build.save_items(path, [_item("a", "g.example"), _item("b", "h.example")])
    sheet = tmp_path / "sheet.csv"
    chosen = label.select(
        build.load_items(path), split="all", module="m3", include_scraped=False, reviewed=False
    )
    label.export_csv(sheet, chosen, tmp_path)
    with sheet.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows[0].update(decision="exclude", comment="off-topic")
    with sheet.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=label.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    assert label.import_csv(sheet, path, "tester") == 1
    items = {i.id: i for i in build.load_items(path)}
    assert items["a"].excluded and items["b"].review is None
    assert "off-topic" in items["a"].note


def test_interactive_records_decisions(tmp_path: Path) -> None:
    path = tmp_path / "golden.jsonl"
    build.save_items(path, [_item("a", "g.example"), _item("b", "h.example")])
    answers = iter(["0", "q"])
    done = label.interactive(
        path, "tester", build.load_items(path), ask=lambda _: next(answers), out=lambda _: None
    )
    assert done == 1
    items = {i.id: i for i in build.load_items(path)}
    assert items["a"].label == 0 and items["a"].labeler == "human"
    assert items["a"].review is not None and items["a"].review.decision == "changed"


def test_real_items_tolerate_withdrawn_raw_posts(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "labels").mkdir()
    (tmp_path / "raw" / "posts.jsonl").write_text(
        json.dumps(
            {
                "platform": "youtube",
                "collector": "youtube",
                "external_id": "abc",
                "url": "https://www.youtube.com/watch?v=abc",
                "author": "Kanał",
                "text": "",
            }
        )
        + "\n"
    )
    labels = [
        {"ref": "youtube:abc", "module": "m1_third_party_ad", "label": 1, "labeler": "agent",
         "confidence": 0.6},
        {"ref": "facebook:gone", "module": "m1_third_party_ad", "label": 0, "labeler": "agent",
         "confidence": 0.6},
    ]  # fmt: skip
    (tmp_path / "labels" / "real.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))
    items = real.real_items(tmp_path)
    assert [i.id for i in items] == ["real-m1-youtube-abc"]
    assert "needs an official API fetch" in items[0].note
    assert not items[0].provenance.headline
    assert real.resolve_text(tmp_path, items[0]) == ""


@pytest.mark.skipif(not (GOLDEN / "golden.jsonl").exists(), reason="no golden set")
def test_committed_golden_set_is_consistent() -> None:
    items = build.load_items(GOLDEN / "golden.jsonl")
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))
    assert {i.module for i in items if i.provenance.method == "demo_site"} == {"m2_risk_disclosure"}
    for item in items:
        if item.render_path:
            assert (GOLDEN / item.render_path).exists(), item.id
