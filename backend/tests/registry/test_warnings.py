from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import Platform, Post
from investwatch.db import repo
from investwatch.pipeline import ai_client
from investwatch.pipeline import analyze as pipeline
from investwatch.pipeline.schemas import AnalyzeResponse
from investwatch.registry.warnings import entity_names, get_index, match_warning


def _post(
    url: str = "https://www.youtube.com/watch?v=abc",
    author: str = "@kanal",
    text: str = "Treść",
    platform: Platform = "youtube",
    author_url: str | None = None,
) -> Post:
    now = datetime.now(UTC)
    return Post(
        id=uuid.uuid4(),
        platform=platform,
        collector="test",
        external_id=url,
        url=url,
        canonical_url=url,
        author=author,
        author_url=author_url,
        text=text,
        lang="pl",
        content_hash="x",
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=None,
        first_seen_at=now,
        last_seen_at=now,
    )


def test_entity_names_split_numbered_rows_and_aliases() -> None:
    cell = (
        "1. Grand Marshall Ltd. z siedzibą w Republice Wysp Marshalla, administrator platformy "
        "(www.grandtrade.exchange) 2. Grand Nova Ltd. z siedzibą we Wspólnocie Dominiki"
    )
    assert entity_names(cell) == ["Grand Marshall Ltd", "Grand Nova Ltd"]
    assert entity_names("Bank Expresse Finances (Expresse Finances banque, EF Bank)") == [
        "Bank Expresse Finances",
        "Expresse Finances banque",
        "EF Bank",
    ]


def test_publisher_domain_on_the_list() -> None:
    warning = match_warning(_post(url="https://www.grandtrade.exchange/pl/start", platform="web"))
    assert warning is not None
    assert warning.method == "domain" and warning.matched_text == "grandtrade.exchange"
    assert warning.name == "Grand Marshall Ltd"
    assert warning.as_of == get_index().as_of  # type: ignore[union-attr]
    assert warning.source_url.startswith("https://www.knf.gov.pl/")


def test_publisher_name_exact_and_fuzzy() -> None:
    exact = match_warning(_post(author="Quantumlux Group"))
    assert exact is not None and exact.method == "name" and exact.name == "Quantumlux Group"
    handle = match_warning(_post(author="@quantumluxgroup"))
    assert handle is not None and handle.method == "name"
    fuzzy = match_warning(_post(author="Quantumlux Grup"))
    assert fuzzy is not None and fuzzy.method == "fuzzy"
    assert match_warning(_post(author="Quantumlux Group"), by_name=False) is None


def test_mentions_and_ordinary_authors_do_not_match() -> None:
    text = "Uwaga na grandtrade.exchange i Quantumlux Group, KNF ostrzega!"
    assert match_warning(_post(author="@KasiaInwestuje", text=text)) is None
    assert match_warning(_post(author="Dom Maklerski BOŚ S.A.", url="https://bossa.pl")) is None


@pytest.fixture
def warned_item() -> CollectedItem:
    return CollectedItem(
        platform="web",
        collector="test",
        external_id="https://grandtrade.exchange/oferta",
        url="https://grandtrade.exchange/oferta",
        author="grandtrade.exchange",
        text="Gwarantujemy zysk 40% rocznie. Powiemy Ci, które akcje kupić jutro.",
    )


def test_pipeline_stores_and_sends_the_flag(
    session: Session, warned_item: CollectedItem, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Any] = []
    real = ai_client.analyze

    def spy(*args: Any, **kwargs: Any) -> tuple[AnalyzeResponse, str]:
        sent.append(kwargs.get("knf_warning"))
        return real(*args, **kwargs)

    monkeypatch.setattr(ai_client, "analyze", spy)
    post_id = pipeline.ingest_item(session, warned_item).post.id
    session.commit()
    outcome = pipeline.analyze_post(post_id)
    assert sent == ["Grand Marshall Ltd"]
    assert outcome.finding_ids
    view = repo.get_finding(session, uuid.UUID(outcome.finding_ids[0]))
    assert view is not None and view.knf_warning is not None
    assert view.knf_warning.name == "Grand Marshall Ltd"
    assert view.model_dump(mode="json")["knf_warning"]["method"] == "domain"


def test_entity_names_end_at_the_platform_clause() -> None:
    cell = "Cream sp. z o.o. za pośrednictwem platformy www.croowdfund.pl"
    assert entity_names(cell) == ["Cream sp. z o.o"]
    assert entity_names("Jan Kowalski posługujący się nazwą FX Pro Signals") == ["Jan Kowalski"]


def test_domains_are_indexed_even_without_a_parsable_name(tmp_path: Any) -> None:
    """A listed domain is the strongest evidence; an unparsable name must not drop it."""
    import json

    from investwatch.registry.warnings import build_index

    snapshot: dict[str, Any] = {
        "source": "https://www.knf.gov.pl/dla_konsumenta/ostrzezenia_publiczne",
        "licence": "test",
        "retrieved_at": "2026-11-21",
        "total_rows": 1,
    }
    snapshot["entities"] = [
        {
            "name": "www.example-scam.pl",
            "identifier": "brak danych",
            "section": "investment_services",
            "art69_points": [],
            "domains": ["example-scam.pl"],
            "final_judgment": False,
            "info": "",
        }
    ]
    path = tmp_path / "w.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    index = build_index(path)
    assert "example-scam.pl" in index.by_domain
    assert index.by_domain["example-scam.pl"].name == "www.example-scam.pl"
