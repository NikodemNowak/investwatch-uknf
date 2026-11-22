"""KNF register: firm source and details, richer sync log (plan 3.7).

Revision ID: 0002_registry
Revises: 0001
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# revision identifiers, used by Alembic.
revision: str = "0002_registry"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("firms") as batch:
        batch.add_column(
            sa.Column("source", sa.String(length=20), nullable=False, server_default="fixture")
        )
        batch.add_column(sa.Column("details", JSON_T, nullable=True))
        batch.create_index("ix_firms_source", ["source"])
    with op.batch_alter_table("registry_sync_log") as batch:
        batch.add_column(sa.Column("source", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("fetched_at", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("total", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("per_kind", JSON_T, nullable=True))
        batch.add_column(sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("registry_sync_log") as batch:
        for column in ("error", "per_kind", "total", "fetched_at", "source"):
            batch.drop_column(column)
    with op.batch_alter_table("firms") as batch:
        batch.drop_index("ix_firms_source")
        batch.drop_column("details")
        batch.drop_column("source")
