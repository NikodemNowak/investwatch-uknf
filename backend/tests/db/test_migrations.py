from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from investwatch.db.models import Base
from investwatch.db.session import get_engine


def test_migrations_match_models(db: None) -> None:
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
