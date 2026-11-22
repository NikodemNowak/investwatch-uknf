"""LLM review state on findings; token count and processing trace on posts (roadmap P1).

Revision ID: 0003
Revises: 0002_registry
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "findings",
        sa.Column("llm_review", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.add_column("posts", sa.Column("token_count", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("trace", JSON_T, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("posts") as batch:
        batch.drop_column("trace")
        batch.drop_column("token_count")
    with op.batch_alter_table("findings") as batch:
        batch.drop_column("llm_review")
