from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from investwatch.db.schemas import FindingView
from investwatch.reports.export import BOM, to_csv, to_row
from investwatch.reports.schemas import M1Row, M2Row, M3Row

REPO = Path(__file__).resolve().parents[3]


def _views() -> list[FindingView]:
    findings = json.loads((REPO / "data/fixtures/findings.json").read_text(encoding="utf-8"))
    posts = {p["id"]: p for p in json.loads((REPO / "data/fixtures/posts.json").read_text("utf-8"))}
    return [FindingView.model_validate({**f, "post": posts[f["post_id"]]}) for f in findings]


def _by_module(module: str) -> list[FindingView]:
    return [f for f in _views() if f.module == module]


def test_m1_row_has_firm_advertiser_text_and_dates() -> None:
    f = _by_module("m1_third_party_ad")[0]
    row = to_row(f)
    assert isinstance(row, M1Row)
    assert row.firm == "Kyrenia Prime Ltd" and row.advertiser == "@InwestujZKasia"
    assert row.ad_text == f.post.text and row.url == f.post.url
    assert row.first_seen_at == f.post.first_seen_at and row.status == "confirmed"


def test_m2_row_lists_failed_rules_with_legal_basis() -> None:
    row = to_row(_by_module("m2_risk_disclosure")[0])
    assert isinstance(row, M2Row)
    assert row.violated_rules[0] == "2. " + row.violated_rules[0].split(". ", 1)[1]
    assert all("(" in r and r.endswith(")") for r in row.violated_rules)
    assert any("MiFID II" in r for r in row.violated_rules)


def test_m3_row_lists_present_art76_elements() -> None:
    row = to_row(_by_module("m3_shadow_advisory")[0])
    assert isinstance(row, M3Row)
    assert row.entity == "Kowalski Family Office"
    assert row.art76_signals[0] == "76a. Rekomendacja spersonalizowana"


def test_csv_has_bom_polish_headers_and_semicolon_option() -> None:
    rows = [to_row(f) for f in _by_module("m1_third_party_ad")]
    out = to_csv("m1_third_party_ad", rows)
    assert out.startswith(BOM)
    parsed = list(csv.reader(io.StringIO(out.removeprefix(BOM))))
    assert parsed[0][:3] == ["Firma inwestycyjna", "Podmiot reklamujący", "Treść reklamy"]
    assert len(parsed) == 1 + len(rows)
    assert parsed[1][8] == "0.940"
    semi = list(csv.reader(io.StringIO(to_csv("m1_third_party_ad", rows, ";")[1:]), delimiter=";"))
    assert semi[0] == parsed[0] and semi[1][8] == "0,940"


def test_csv_neutralises_formulas() -> None:
    f = _by_module("m3_shadow_advisory")[0]
    evil = f.model_copy(update={"advertiser": '=HYPERLINK("http://x")'})
    out = to_csv("m3_shadow_advisory", [to_row(evil)])
    parsed = list(csv.reader(io.StringIO(out[1:])))
    assert parsed[1][0].startswith("'=")
