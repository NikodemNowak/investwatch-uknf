"""Posts keep how they were obtained (access mode, legal basis, synthetic flag) for the UI.

Revision ID: 0008_post_provenance
Revises: 0007_render_hash
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_post_provenance"
down_revision: str | Sequence[str] | None = "0007_render_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    """Add `posts.provenance`."""
    with op.batch_alter_table("posts") as batch:
        batch.add_column(sa.Column("provenance", JSON_T, nullable=True))


def downgrade() -> None:
    """Drop `posts.provenance`."""
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("provenance")
