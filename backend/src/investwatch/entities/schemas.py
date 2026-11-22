"""Shapes of the result aggregator (`GET /api/entities`)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from investwatch.core.schemas import ModuleId, Platform, RegisteredFirm, RiskLevel
from investwatch.db.schemas import FindingView
from investwatch.registry.schemas import KnfWarning

EntityKind = Literal["firm", "advertiser"]
"""`firm`: matched to a register entry; `advertiser`: a publisher, author or domain."""
RegisterState = Literal["knf", "fictional", "absent"]
"""`knf`: in the KNF register; `fictional`: a demo firm; `absent`: not matched to the register."""


class EntitySummary(BaseModel):
    """One entity with its findings from every module merged into counts and extremes."""

    key: str
    """Stable id: `firm:<uuid>` or `name:<normalised name>`."""
    kind: EntityKind
    name: str
    firm: RegisteredFirm | None = None
    knf_register: RegisterState
    knf_warning: KnfWarning | None = None
    """First KNF warning-list match among the entity's findings."""
    modules: dict[ModuleId, int]
    """Findings per module (every module present, zero when none)."""
    total: int
    open: int
    """Findings still waiting for a decision (`new` or `in_review`)."""
    confirmed: int
    dismissed: int
    highest_risk: RiskLevel
    max_score: float
    occurrences: int
    """Locations over all findings (each finding counts its duplicates too)."""
    platforms: list[Platform]
    first_seen_at: datetime
    last_seen_at: datetime
    latest_finding_id: UUID
    latest_at: datetime
    """`created_at` of the newest finding."""


class EntitiesPage(BaseModel):
    """Aggregated entities, most serious first."""

    items: list[EntitySummary]
    total: int
    findings: int
    """Findings that went into the aggregation."""
    truncated: bool
    """True when more findings matched than the aggregator reads."""


class EntityDetail(EntitySummary):
    """An entity with its findings, newest first (the drill-down)."""

    findings: list[FindingView]
