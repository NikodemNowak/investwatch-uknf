"""Report rows per module; field titles are the (Polish) CSV column headers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from investwatch.core.schemas import ModuleId, Platform, RiskLevel, Status


class ReportRow(BaseModel):
    """Columns shared by every module report.

    One row per location: a duplicate (same text and layout elsewhere) repeats the finding's
    verdict under its own URL, author and dates, so no place where the material ran is lost.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: UUID = Field(title="ID rekordu")
    url: str = Field(title="URL")
    platform: Platform = Field(title="Platforma")
    score: float = Field(title="Wynik")
    risk_level: RiskLevel = Field(title="Poziom ryzyka")
    status: Status = Field(title="Status")
    first_seen_at: datetime = Field(title="Pierwsze wystąpienie")
    """First sighting of this location (URL)."""
    last_seen_at: datetime = Field(title="Ostatnie wystąpienie")
    occurrences: int = Field(default=1, title="Wystąpienia w grupie")
    """Locations with the same text and layout; one row each, same `finding_id`."""


class M1Row(ReportRow):
    """M1: an investment firm advertised by a third party (finfluencer)."""

    firm: str = Field(title="Firma inwestycyjna")
    advertiser: str = Field(title="Podmiot reklamujący")
    ad_text: str = Field(title="Treść reklamy")


class M2Row(ReportRow):
    """M2: a firm's own marketing material with failed risk-disclosure rules."""

    firm: str = Field(title="Firma")
    material: str = Field(title="Materiał")
    violated_rules: list[str] = Field(title="Naruszone reguły (podstawa prawna)")


class M3Row(ReportRow):
    """M3: an unregistered entity offering what looks like investment advice."""

    entity: str = Field(title="Podmiot")
    offer_text: str = Field(title="Treść oferty")
    art76_signals: list[str] = Field(title="Sygnały art. 76")


class Report(BaseModel):
    """Response of `GET /api/reports/{module}.json`."""

    module: ModuleId
    generated_at: datetime
    count: int
    truncated: bool
    """True when more findings matched than `limit`."""
    items: list[M1Row] | list[M2Row] | list[M3Row]
