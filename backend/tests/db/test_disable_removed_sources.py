from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from investwatch.collectors.registry import COLLECTORS


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", "investwatch.db:migrations")
    return config


def test_upgrade_disables_sources_of_removed_collectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    from investwatch.config import get_settings

    get_settings.cache_clear()
    command.upgrade(_config(), "0004_labels")
    engine = create_engine(url)
    rows = {"search": uuid.uuid4(), "discovery": uuid.uuid4(), "web": uuid.uuid4()}
    with engine.begin() as conn:
        for collector, sid in rows.items():
            conn.execute(
                text(
                    "INSERT INTO sources (id, name, collector, target, cron, enabled, created_at)"
                    " VALUES (:id, :name, :collector, 'x', '0 * * * *', 1, CURRENT_TIMESTAMP)"
                ),
                {"id": sid.hex, "name": collector, "collector": collector},
            )

    command.upgrade(_config(), "head")

    with engine.connect() as conn:
        enabled = dict(conn.execute(text("SELECT collector, enabled FROM sources")).all())
    engine.dispose()
    assert enabled == {"search": 0, "discovery": 0, "web": 1}


def test_migration_keeps_the_current_registry() -> None:
    import importlib.util

    import investwatch.db.migrations as migrations

    path = Path(migrations.__file__).parent / "versions" / "0005_disable_removed_sources.py"
    spec = importlib.util.spec_from_file_location("m0005", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    added_later = {"microsoft_ad_library"}  # sources created after 0005 are never touched by it
    assert set(migration.KEPT_COLLECTORS) == set(COLLECTORS) - added_later
