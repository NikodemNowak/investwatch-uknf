"""Initial schema (plan 3.4).

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
VECTOR_T = sa.JSON().with_variant(Vector(1024), "postgresql")

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("handle", sa.String(length=300), nullable=True),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "firms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("country", sa.String(length=10), nullable=True),
        sa.Column("supervisor", sa.String(length=100), nullable=True),
        sa.Column("services", JSON_T, nullable=False),
        sa.Column("register_url", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_firms_name"), "firms", ["name"], unique=False)
    op.create_table(
        "registry_sync_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("renamed", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", JSON_T, nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("collector", sa.String(length=50), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("module_hint", sa.String(length=50), nullable=True),
        sa.Column("cron", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "firm_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=300), nullable=False),
        sa.Column("alias_type", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firm_id", "alias", "alias_type", name="uq_firm_alias"),
    )
    op.create_index(op.f("ix_firm_aliases_alias"), "firm_aliases", ["alias"], unique=False)
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("collector", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=False),
        sa.Column("author_url", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=10), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", VECTOR_T, nullable=True),
        sa.Column("html_key", sa.Text(), nullable=True),
        sa.Column("render_key", sa.Text(), nullable=True),
        sa.Column("screenshot_keys", JSON_T, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duplicate_of", sa.Uuid(), nullable=True),
        sa.Column("fetch_status", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["duplicate_of"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "external_id", name="uq_posts_platform_ext"),
    )
    op.create_index(op.f("ix_posts_canonical_url"), "posts", ["canonical_url"], unique=False)
    op.create_index(op.f("ix_posts_content_hash"), "posts", ["content_hash"], unique=False)
    op.create_index(op.f("ix_posts_duplicate_of"), "posts", ["duplicate_of"], unique=False)
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("items_new", sa.Integer(), nullable=False),
        sa.Column("items_seen", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scrape_runs_source_id"), "scrape_runs", ["source_id"], unique=False)
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("quotes", JSON_T, nullable=False),
        sa.Column("firm_id", sa.Uuid(), nullable=True),
        sa.Column("firm_match", JSON_T, nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("advertiser", sa.String(length=300), nullable=True),
        sa.Column("rules", JSON_T, nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("used_llm", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["firm_id"], ["firms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "module", name="uq_findings_post_module"),
    )
    op.create_index("ix_findings_created_at", "findings", ["created_at"], unique=False)
    op.create_index(op.f("ix_findings_module"), "findings", ["module"], unique=False)
    op.create_index(op.f("ix_findings_risk_level"), "findings", ["risk_level"], unique=False)
    op.create_index(op.f("ix_findings_status"), "findings", ["status"], unique=False)
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("label", sa.Integer(), nullable=False),
        sa.Column("rule_labels", JSON_T, nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("labeler", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("labels")
    op.drop_index(op.f("ix_findings_status"), table_name="findings")
    op.drop_index(op.f("ix_findings_risk_level"), table_name="findings")
    op.drop_index(op.f("ix_findings_module"), table_name="findings")
    op.drop_index("ix_findings_created_at", table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_scrape_runs_source_id"), table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_index(op.f("ix_posts_duplicate_of"), table_name="posts")
    op.drop_index(op.f("ix_posts_content_hash"), table_name="posts")
    op.drop_index(op.f("ix_posts_canonical_url"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_firm_aliases_alias"), table_name="firm_aliases")
    op.drop_table("firm_aliases")
    op.drop_table("sources")
    op.drop_table("settings")
    op.drop_table("registry_sync_log")
    op.drop_index(op.f("ix_firms_name"), table_name="firms")
    op.drop_table("firms")
    op.drop_table("entities")
