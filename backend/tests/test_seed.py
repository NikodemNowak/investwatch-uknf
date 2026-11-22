from __future__ import annotations

from sqlalchemy import func, select

from investwatch.db.models import FindingRow, PostRow, SourceRow
from investwatch.db.session import session_scope
from investwatch.seed import DEMO_SOURCES, seed_base


def test_seed_is_idempotent_and_inserts_no_findings(db: None) -> None:
    with session_scope() as s:
        first = seed_base(s)
    with session_scope() as s:
        second = seed_base(s)
        assert s.scalar(select(func.count()).select_from(FindingRow)) == 0
        assert s.scalar(select(func.count()).select_from(PostRow)) == 0
        assert s.scalar(select(func.count()).select_from(SourceRow)) == len(DEMO_SOURCES)
    assert first["sources_added"] == len(DEMO_SOURCES) and second["sources_added"] == 0
    assert first["register_firms"] > 100 and first["demo_firms"] >= 2
