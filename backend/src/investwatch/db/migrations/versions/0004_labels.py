"""Labels for calibration: golden-set items without a post, analyst decisions (plan 2.6).

Revision ID: 0004_labels
Revises: 0003
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# revision identifiers, used by Alembic.
revision: str = "0004_labels"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("labels") as batch:
        batch.alter_column("post_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("ref", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("split", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("origin", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("provenance", JSON_T, nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_labels_module", ["module"])
        batch.create_index("ix_labels_post_id", ["post_id"])
        batch.create_unique_constraint("uq_labels_source_ref", ["source", "ref"])


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM labels WHERE post_id IS NULL")
    with op.batch_alter_table("labels") as batch:
        batch.drop_constraint("uq_labels_source_ref", type_="unique")
        batch.drop_index("ix_labels_post_id")
        batch.drop_index("ix_labels_module")
        for column in ("updated_at", "provenance", "origin", "split", "score", "ref"):
            batch.drop_column(column)
        batch.alter_column("post_id", existing_type=sa.Uuid(), nullable=False)
