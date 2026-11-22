from __future__ import annotations

from investwatch.pipeline.dedup import canonical_url, content_hash


def test_canonical_url_strips_tracking() -> None:
    url = "HTTPS://Example.COM/a?utm_source=x&b=2&fbclid=1&a=1#frag"
    assert canonical_url(url) == "https://example.com/a?a=1&b=2"


def test_content_hash_ignores_case_and_spacing() -> None:
    assert content_hash("Zysk  38%\nrocznie") == content_hash("zysk 38% rocznie")
    assert content_hash("a") != content_hash("b")


# ---------------------------------------------------------------- P3: text + layout key

import csv  # noqa: E402
import io  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from sqlalchemy.orm import Session  # noqa: E402

from investwatch.collectors import sample  # noqa: E402
from investwatch.collectors.schemas import CollectedItem  # noqa: E402
from investwatch.core.schemas import RenderSnapshot  # noqa: E402
from investwatch.db import repo  # noqa: E402
from investwatch.pipeline import analyze as pipeline  # noqa: E402
from investwatch.pipeline.dedup import render_hash  # noqa: E402
from investwatch.reports.export import BOM, to_csv, to_rows  # noqa: E402

TEXT = "Fundusz Aurora Wzrost: średni zysk 18% rocznie w ostatnich 3 latach. Dołącz już dziś."


def _resized(render: RenderSnapshot, px: float) -> RenderSnapshot:
    """The same blocks with the last one set in `px` font (a different layout)."""
    viewports = {
        vp: [*blocks[:-1], blocks[-1].model_copy(update={"font_px": px})]
        for vp, blocks in render.viewports.items()
    }
    return render.model_copy(update={"viewports": viewports})


def test_render_hash_tracks_layout_not_identity() -> None:
    render = sample.load_render_snapshot()
    assert render_hash(None) is None
    assert render_hash(render) == render_hash(render.model_copy(deep=True))
    assert render_hash(render) != render_hash(_resized(render, 30.0))
    # Sub-pixel noise does not make a new layout.
    assert render_hash(_resized(render, 16.2)) == render_hash(_resized(render, 16.4))


def _page(url: str, render: RenderSnapshot | None) -> CollectedItem:
    return CollectedItem(
        platform="web",
        collector="web",
        external_id=url,
        url=url,
        author="demo-sites",
        text=TEXT,
        render=render,
    )


def test_same_text_different_layout_gives_two_findings(db: None, session: Session) -> None:
    render = sample.load_render_snapshot()
    ok = pipeline.ingest_item(session, _page("http://demo-sites/a.html", render)).post.id
    tiny = pipeline.ingest_item(
        session, _page("http://demo-sites/b.html", _resized(render, 30.0))
    ).post.id
    session.commit()
    first = pipeline.analyze_post(ok)
    second = pipeline.analyze_post(tiny)
    assert second.duplicate_of is None
    assert first.finding_ids and second.finding_ids
    assert set(first.finding_ids).isdisjoint(second.finding_ids)


def test_same_layout_on_another_url_joins_the_group(db: None, session: Session) -> None:
    render = sample.load_render_snapshot()
    a = pipeline.ingest_item(session, _page("http://demo-sites/a.html", render)).post.id
    b = pipeline.ingest_item(session, _page("http://demo-sites/copy.html", render)).post.id
    session.commit()
    assert pipeline.analyze_post(a).finding_ids
    assert pipeline.analyze_post(b).duplicate_of == str(a)


def _social(url: str, author: str, seen: datetime) -> CollectedItem:
    return CollectedItem(
        platform="instagram",
        collector="file_import",
        external_id=url,
        url=url,
        author=author,
        text="Otwórz konto w PrimeFX24 z moim kodem KASIA i zarabiaj 30% miesięcznie!",
        published_at=seen,
    )


def test_same_content_two_urls_is_one_group_with_two_occurrences(
    db: None, session: Session
) -> None:
    t0 = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    first = pipeline.ingest_item(session, _social("https://instagram.example/p/1", "@kasia", t0))
    session.commit()
    outcome = pipeline.analyze_post(first.post.id)
    assert outcome.finding_ids
    repo.upsert_post(  # a later sighting of the first post
        session,
        first.post.model_copy(update={"last_seen_at": t0 + timedelta(days=2)}),
    )
    second = pipeline.ingest_item(session, _social("https://tiktok.example/v/9", "@kasia2", t0))
    session.commit()
    dup = pipeline.analyze_post(second.post.id)
    assert dup.duplicate_of == str(first.post.id) and dup.finding_ids == []

    view = repo.get_finding(session, uuid.UUID(outcome.finding_ids[0]))
    assert view is not None
    assert view.duplicates == 1 and len(view.occurrences) == 2
    assert [o.url for o in view.occurrences] == [
        "https://instagram.example/p/1",
        "https://tiktok.example/v/9",
    ]
    assert view.first_seen_at is not None and view.last_seen_at is not None
    assert view.last_seen_at >= t0 + timedelta(days=2)
    assert view.first_seen_at <= view.occurrences[1].first_seen_at

    rows = to_rows(view)
    assert [r.url for r in rows] == [o.url for o in view.occurrences]
    assert {r.occurrences for r in rows} == {2} and len({r.finding_id for r in rows}) == 1
    parsed = list(csv.reader(io.StringIO(to_csv(view.module, rows).removeprefix(BOM))))
    header = parsed[0]
    assert "Pierwsze wystąpienie" in header and "Ostatnie wystąpienie" in header
    assert "Wystąpienia w grupie" in header and len(parsed) == 3


def test_provenance_marks_fictional_material() -> None:
    from investwatch.collectors.schemas import CollectedItem
    from investwatch.pipeline.dedup import post_provenance

    def item(url: str, raw: dict[str, object] | None, collector: str = "web") -> CollectedItem:
        return CollectedItem(
            platform="web",
            collector=collector,
            external_id=url,
            url=url,
            author="a",
            text="t",
            raw=raw,
        )

    real = post_provenance(item("https://www.xtb.com/pl", {"access_mode": "crawler"}))
    assert real.access_mode == "crawler" and not real.synthetic
    assert post_provenance(item("http://demo-sites/ok.html", {})).synthetic
    assert post_provenance(item("https://wislacapital.example/x", None)).synthetic
    imported = post_provenance(
        item("https://x.pl", {"synthetic": True, "provenance_note": "DANE SYNTETYCZNE"})
    )
    assert imported.synthetic and imported.note == "DANE SYNTETYCZNE"
    blocked = item("https://x.pl", {}).model_copy(update={"error": "disallowed by robots.txt"})
    assert post_provenance(blocked).fetch_error == "disallowed by robots.txt"
