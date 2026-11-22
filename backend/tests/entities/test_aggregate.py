from __future__ import annotations

from investwatch.entities.aggregate import _known, normalize_name


def test_normalize_name_ignores_case_at_and_spaces() -> None:
    assert normalize_name("  @InwestujZKasia ") == "inwestujzkasia"
    assert normalize_name("Marcin  |  Giełda") == "marcin | giełda"
    assert normalize_name("@") == ""


def test_placeholder_authors_are_no_entity() -> None:
    assert not _known("(wklejony tekst)") and not _known("  ") and _known("@sygnaly.vip")


# ------------------------------------------------ one entity per firm (quality round)

import json  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from investwatch.db.schemas import FindingView  # noqa: E402
from investwatch.entities.aggregate import aggregate  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures"


def _firm(name: str) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)),
        "name": name,
        "aliases": [],
        "domains": ["firma.example"],
        "handles": [],
        "kind": "zagraniczna_bez_oddzialu",
        "country": "SK",
        "services": ["A1", "A5"],
        "register_url": "https://www.knf.gov.pl/",
    }


def _finding(
    module: str,
    author: str,
    firm: dict[str, Any] | None,
    url: str = "https://firma.example/a",
    on: str = "author",
    advertiser: str | None = None,
) -> FindingView:
    post = json.loads((FIXTURES / "posts.json").read_text())[0]
    post = post | {"id": str(uuid.uuid4()), "url": url, "author": author, "platform": "web"}
    match = (
        {"firm": firm, "confidence": 1.0, "method": "domain", "matched_text": "x", "on": on}
        if firm
        else None
    )
    return FindingView.model_validate(
        {
            "id": str(uuid.uuid4()),
            "post_id": post["id"],
            "module": module,
            "score": 0.5,
            "risk_level": "medium",
            "explanation": "",
            "quotes": [],
            "firm": firm,
            "firm_match": match,
            "advertiser": advertiser,
            "rules": [],
            "model": "rules-v2",
            "used_llm": False,
            "status": "new",
            "created_at": "2026-11-21T10:00:00Z",
            "post": post,
        }
    )


def test_publisher_without_firm_joins_the_firm_it_publishes_for() -> None:
    xtb = _firm("XTB S.A.")
    findings = [
        _finding("m2_risk_disclosure", "X-Trade Brokers DM S.A. (XTB)", xtb),
        _finding(
            "m3_shadow_advisory",
            "X-Trade Brokers DM S.A. (XTB)",
            None,
            url="https://firma.example/b",
            advertiser="X-Trade Brokers DM S.A. (XTB)",
        ),
    ]
    entities = aggregate(findings, {})
    assert [e.name for e in entities] == ["XTB S.A."]
    assert entities[0].modules["m3_shadow_advisory"] == 1 and entities[0].total == 2


def test_two_register_records_of_one_firm_are_one_entity() -> None:
    branch, passport = _firm("Finax, o.c.p., a.s."), _firm("Finax o.c.p., a.s.")
    findings = [
        _finding("m2_risk_disclosure", "Finax o.c.p., a.s.", branch),
        _finding("m2_risk_disclosure", "finax.eu", passport, url="https://firma.example/c"),
    ]
    entities = aggregate(findings, {})
    assert len(entities) == 1 and entities[0].total == 2
    assert entities[0].key == f"firm:{branch['id']}" or entities[0].key == f"firm:{passport['id']}"


def test_influencer_promoting_a_firm_stays_its_own_entity() -> None:
    firm = _firm("Kyrenia Prime Ltd")
    findings = [
        _finding("m2_risk_disclosure", "kyrenia.example", firm),
        _finding(
            "m1_third_party_ad",
            "@kasia",
            firm,
            url="https://www.youtube.com/watch?v=1",
            on="content",
            advertiser="@kasia",
        ),
    ]
    names = {e.name for e in aggregate(findings, {})}
    assert names == {"Kyrenia Prime Ltd", "@kasia"}
