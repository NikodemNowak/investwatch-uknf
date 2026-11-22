from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from investwatch.db import repo
from investwatch.jobs.tasks import next_run, tick_sources


def test_next_run_uses_cron() -> None:
    after = datetime(2026, 11, 21, 13, 7, tzinfo=UTC)
    assert next_run("*/15 * * * *", after) == datetime(2026, 11, 21, 13, 15, tzinfo=UTC)


def test_tick_queues_due_sources_once(db: None, session: Session) -> None:
    source = repo.create_source(
        session, name="s", collector="sample", target="", cron="0 * * * *", enabled=True
    )
    repo.create_source(session, name="off", collector="sample", target="", enabled=False)
    session.commit()
    assert tick_sources() == [str(source.id)]
    assert tick_sources() == []  # rescheduled to the next full hour
    runs = repo.list_runs(session, source.id)
    assert runs[0].status == "ok" and runs[0].items_new == 10
