from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from investwatch.collectors.sample import load_findings, load_posts
from investwatch.db import repo
from investwatch.db.schemas import FindingFilters, Thresholds


def test_upsert_post_detects_new_and_changed(session: Session) -> None:
    post = load_posts()[0]
    first = repo.upsert_post(session, post)
    assert first.created and first.changed

    again = repo.upsert_post(session, post.model_copy(update={"id": uuid.uuid4()}))
    assert not again.created and not again.changed
    assert again.post.id == post.id  # keeps the stored id

    edited = post.model_copy(update={"text": "inny tekst", "content_hash": "x" * 64})
    assert repo.upsert_post(session, edited).changed


def test_save_findings_keeps_analyst_status(seeded: None, session: Session) -> None:
    confirmed = next(f for f in load_findings() if f.status == "confirmed")
    rerun = confirmed.model_copy(update={"id": uuid.uuid4(), "status": "new", "score": 0.5})
    [saved] = repo.save_findings(session, [rerun])
    assert saved.id == confirmed.id
    assert saved.status == "confirmed"
    view = repo.get_finding(session, confirmed.id)
    assert view is not None and view.score == 0.5


def test_list_findings_filters(seeded: None, session: Session) -> None:
    assert repo.list_findings(session, FindingFilters()).total == 12
    m2 = repo.list_findings(session, FindingFilters(module="m2_risk_disclosure"))
    assert m2.total == 4 and all(f.module == "m2_risk_disclosure" for f in m2.items)
    high = repo.list_findings(session, FindingFilters(risk_level="high", sort="score"))
    scores = [f.score for f in high.items]
    assert scores == sorted(scores, reverse=True) and all(
        f.risk_level == "high" for f in high.items
    )
    since = repo.list_findings(
        session, FindingFilters(date_from=datetime(2026, 11, 20, tzinfo=UTC))
    )
    assert since.total > 0 and all(
        f.created_at >= datetime(2026, 11, 20, tzinfo=UTC) for f in since.items
    )
    yt = repo.list_findings(session, FindingFilters(platform="youtube"))
    assert yt.total > 0 and all(f.post.platform == "youtube" for f in yt.items)
    page = repo.list_findings(session, FindingFilters(page=3, page_size=5))
    assert len(page.items) == 2
    assert repo.list_findings(session, FindingFilters(q="primefx24")).total > 0


def test_finding_firm_round_trip(seeded: None, session: Session) -> None:
    original = next(f for f in load_findings() if f.firm is not None)
    view = repo.get_finding(session, original.id)
    assert view is not None
    assert view.firm is not None and original.firm is not None
    # The register sync merges demo URL prefixes into fixture firms (data/registry/demo_firms.json).
    assert (view.firm.id, view.firm.name) == (original.firm.id, original.firm.name)
    assert set(original.firm.domains) <= set(view.firm.domains)


def test_trend_counts_by_day(seeded: None, session: Session) -> None:
    series = repo.trend(session, "day", date(2026, 11, 14), date(2026, 11, 21))
    assert len(series.points) == 8 * 3
    assert sum(p.total for p in series.points) == 12
    weekly = repo.trend(session, "week", date(2026, 11, 14), date(2026, 11, 21))
    assert sum(p.total for p in weekly.points) == 12


def test_trend_auto_is_daily_when_data_spans_days(seeded: None, session: Session) -> None:
    now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    series = repo.trend_auto(session, now)
    assert series.bucket == "day" and series.end == date(2026, 11, 22)
    assert len({p.bucket_start for p in series.points}) == 14


def test_trend_auto_is_hourly_when_everything_is_recent(seeded: None, session: Session) -> None:
    from sqlalchemy import update

    from investwatch.db.models import FindingRow

    now = datetime(2026, 11, 21, 18, 40, tzinfo=UTC)
    session.execute(update(FindingRow).values(created_at=now - timedelta(hours=3)))
    session.flush()
    series = repo.trend_auto(session, now)
    assert series.bucket == "hour"
    hours = sorted({p.bucket_at for p in series.points if p.bucket_at})
    assert len(hours) == 24 and hours[-1] == datetime(2026, 11, 21, 18, 0, tzinfo=UTC)
    assert sum(p.total for p in series.points) == 12
    busy = [p for p in series.points if p.total]
    assert {p.bucket_at for p in busy} == {datetime(2026, 11, 21, 15, 0, tzinfo=UTC)}
    # Two days of material: 48 hourly buckets, still real timestamps.
    session.execute(update(FindingRow).values(created_at=now - timedelta(hours=30)))
    session.flush()
    assert len({p.bucket_at for p in repo.trend_auto(session, now).points}) == 48


def test_thresholds_default_and_update(session: Session) -> None:
    assert repo.get_thresholds(session) == Thresholds(
        m1_third_party_ad=0.2, m2_risk_disclosure=0.3, m3_shadow_advisory=0.12
    )
    repo.set_thresholds(session, Thresholds(m2_risk_disclosure=0.4))
    assert repo.get_thresholds(session).for_module("m2_risk_disclosure") == 0.4


def test_summary(seeded: None, session: Session) -> None:
    summary = repo.summary(session)
    assert summary.findings == 12 and summary.posts == 10
    assert {m.module for m in summary.modules} == {
        "m1_third_party_ad",
        "m2_risk_disclosure",
        "m3_shadow_advisory",
    }


def test_default_thresholds_are_the_trained_ones() -> None:
    """Screen = evaluation: the shipped defaults equal what `make train` chose on train CV."""
    import json
    from pathlib import Path

    import pytest

    trained = (
        Path(__file__).resolve().parents[3]
        / "ai/src/investwatch_ai/classifier/weights/thresholds.json"
    )
    if not trained.exists():
        pytest.skip("ai/ not present (e.g. Docker build)")
    values = json.loads(trained.read_text(encoding="utf-8"))["thresholds"]
    assert Thresholds().as_dict() == values
