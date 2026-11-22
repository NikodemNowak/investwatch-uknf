"""Disable sources whose collector was removed with the compliance clean-up (ADR 0008).

Databases created before PR #17 may still hold `search`/`discovery` sources. Their collectors
no longer exist, so the rows are switched off; they stay for the audit trail.

Revision ID: 0005_disable_removed_sources
Revises: 0004_labels
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_disable_removed_sources"
down_revision: str | Sequence[str] | None = "0004_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of `collectors/registry.py` at this revision: migrations must not import app code.
KEPT_COLLECTORS = ("manual", "web", "site", "sample", "youtube", "meta_ad_library", "tiktok")


def upgrade() -> None:
    """Switch off every source whose collector no longer exists."""
    sources = sa.table(
        "sources", sa.column("collector", sa.String), sa.column("enabled", sa.Boolean)
    )
    op.execute(
        sources.update().where(sources.c.collector.not_in(KEPT_COLLECTORS)).values(enabled=False)
    )


def downgrade() -> None:
    """Data-only migration: which rows were enabled before is not recorded, so nothing to undo."""
