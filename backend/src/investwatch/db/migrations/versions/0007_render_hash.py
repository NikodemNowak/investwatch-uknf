"""Posts get a layout fingerprint: exact duplicates need the same text *and* layout.

Revision ID: 0007_render_hash
Revises: 0006_knf_warning
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_render_hash"
down_revision: str | Sequence[str] | None = "0006_knf_warning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `posts.render_hash`."""
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("render_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop `posts.render_hash`."""
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("render_hash")
