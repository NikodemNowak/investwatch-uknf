"""SQLAlchemy ORM tables (plan section 3.4).

Postgres is the target; JSON/vector columns fall back to plain JSON on SQLite so the test
suite runs without a database server.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeEngine

EMBEDDING_DIM = 1024

JsonType: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")
VectorType: TypeEngine[Any] = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")


def utcnow() -> datetime:
    """Return the current time, timezone-aware."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all tables."""


class SourceRow(Base):
    """A monitored source: collector + target + schedule."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    collector: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(Text)
    module_hint: Mapped[str | None] = mapped_column(String(50))
    cron: Mapped[str] = mapped_column(String(100), default="0 */6 * * *")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScrapeRunRow(Base):
    """One execution of a source."""

    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class PostRow(Base):
    """A collected publication (`core.schemas.Post`)."""

    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_posts_platform_ext"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(20))
    collector: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, index=True)
    author: Mapped[str] = mapped_column(String(300))
    author_url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str | None] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    render_hash: Mapped[str | None] = mapped_column(String(64))
    """`pipeline.dedup.render_hash`: layout fingerprint; None for posts without a render."""
    embedding: Mapped[list[float] | None] = mapped_column(VectorType)
    html_key: Mapped[str | None] = mapped_column(Text)
    render_key: Mapped[str | None] = mapped_column(Text)
    screenshot_keys: Mapped[dict[str, str]] = mapped_column(JsonType, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), index=True
    )
    fetch_status: Mapped[str] = mapped_column(String(20), default="ok")
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    token_count: Mapped[int | None] = mapped_column(Integer)
    """Tokens of the analysed text, counted by the embedding model's tokenizer."""
    trace: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    """`db.schemas.ProcessingTrace`: what the pipeline did with the post, stage by stage."""
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    """`core.schemas.PostProvenance`: access mode, legal basis, fetch time, synthetic flag."""


class FirmRow(Base):
    """An investment firm from the KNF registers."""

    __tablename__ = "firms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(10))
    supervisor: Mapped[str | None] = mapped_column(String(100))
    services: Mapped[list[str]] = mapped_column(JsonType, default=list)
    register_url: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(20), default="fixture", index=True)
    """`knf` (register sync), `fixture` or `demo` (fictional firms)."""
    details: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    """Register facts for the UI: legal form, former names, address, notes."""


class FirmAliasRow(Base):
    """Alternative identifiers of a firm used for matching."""

    __tablename__ = "firm_aliases"
    __table_args__ = (UniqueConstraint("firm_id", "alias", "alias_type", name="uq_firm_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("firms.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(300), index=True)
    alias_type: Mapped[str] = mapped_column(String(20))
    """`former_name`, `trade_name`, `brand`, `handle` or `domain`."""


class EntityRow(Base):
    """Advertisers, finfluencers and M3 entities."""

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300))
    handle: Mapped[str | None] = mapped_column(String(300))
    platform: Mapped[str | None] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(Text)


class FindingRow(Base):
    """Result of one module for one post (`core.schemas.Finding`)."""

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("post_id", "module", name="uq_findings_post_module"),
        Index("ix_findings_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    module: Mapped[str] = mapped_column(String(40), index=True)
    score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(10), index=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    quotes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    firm_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("firms.id", ondelete="SET NULL"))
    firm_match: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL")
    )
    advertiser: Mapped[str | None] = mapped_column(String(300))
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    model: Mapped[str] = mapped_column(String(200), default="")
    used_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_review: Mapped[str] = mapped_column(String(20), default="none", server_default="none")
    """`core.schemas.LlmReviewState`."""
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    knf_warning: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    """`registry.schemas.KnfWarning`: the publisher is on the KNF public warning list."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LabelRow(Base):
    """Ground-truth labels for calibration.

    `source="golden"`: a golden-set item; it has no post, so `score` holds the score the
    analysis gave it (`make eval`, loaded by `seed`). `source="analyst"`: a record the analyst
    confirmed (1) or dismissed (0); its score is read live from the finding.
    """

    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("source", "ref", name="uq_labels_source_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    module: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[int] = mapped_column(Integer)
    rule_labels: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    source: Mapped[str] = mapped_column(String(20))
    """`golden` or `analyst`."""
    ref: Mapped[str | None] = mapped_column(String(200))
    """Golden item id, or `finding:<id>` for analyst labels (one label per finding)."""
    score: Mapped[float | None] = mapped_column(Float)
    split: Mapped[str | None] = mapped_column(String(10))
    origin: Mapped[str | None] = mapped_column(String(20))
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    labeler: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SettingRow(Base):
    """Key-value runtime settings (thresholds, selected model)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JsonType)


class RegistrySyncLogRow(Base):
    """One KNF register synchronisation."""

    __tablename__ = "registry_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    added: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    renamed: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(String(20))
    """`live` or `snapshot`."""
    fetched_at: Mapped[str | None] = mapped_column(String(40))
    total: Mapped[int | None] = mapped_column(Integer)
    per_kind: Mapped[dict[str, int] | None] = mapped_column(JsonType)
    error: Mapped[str | None] = mapped_column(Text)
