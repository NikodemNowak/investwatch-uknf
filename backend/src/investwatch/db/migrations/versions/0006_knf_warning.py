"""Findings remember whether the publisher is on the KNF public warning list.

Revision ID: 0006_knf_warning
Revises: 0005_disable_removed_sources
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# revision identifiers, used by Alembic.
revision: str = "0006_knf_warning"
down_revision: str | Sequence[str] | None = "0005_disable_removed_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `findings.knf_warning`."""
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("knf_warning", JSON_T, nullable=True))


def downgrade() -> None:
    """Drop `findings.knf_warning`."""
    with op.batch_alter_table("findings") as batch:
        batch.drop_column("knf_warning")
