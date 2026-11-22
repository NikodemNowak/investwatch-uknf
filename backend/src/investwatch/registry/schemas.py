"""Shapes of the KNF register module."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from investwatch.core.schemas import FirmKind, RegisteredFirm

FIRM_NAMESPACE = uuid.UUID("6f1b2c1e-5a0d-4d61-9a43-2b1c7b0e9a11")
"""uuid5 namespace for stable firm ids derived from the register kind and name."""

FirmSource = Literal["knf", "fixture", "demo"]


class KnfRecord(BaseModel):
    """One entity parsed from a KNF register page, with everything the matcher can use."""

    kind: FirmKind
    name: str
    legal_form: str | None = None
    former_names: list[str] = Field(default_factory=list)
    trade_names: list[str] = Field(default_factory=list)
    former_trade_names: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    """Registrable domains (or `host/path` prefixes) listed as current."""
    former_domains: list[str] = Field(default_factory=list)
    """Struck-through domains: kept for the analyst, never used for matching."""
    country: str | None = None
    """ISO 3166-1 alpha-2."""
    supervisor: str | None = None
    address: str | None = None
    services: list[str] = Field(default_factory=list)
    """MiFID II Annex I codes, e.g. ["A1", "A5", "B1"]."""
    authorized_at: str | None = None
    register_url: str
    notes: str | None = None

    @property
    def firm_id(self) -> uuid.UUID:
        """Stable id: the same entity keeps its id across syncs."""
        return uuid.uuid5(FIRM_NAMESPACE, f"{self.kind}:{self.name.casefold()}")

    def to_firm(self) -> RegisteredFirm:
        """Convert to the contract model used by matching and findings."""
        aliases = list(dict.fromkeys([*self.trade_names, *self.former_names]))
        return RegisteredFirm(
            id=self.firm_id,
            name=self.name,
            aliases=aliases,
            domains=list(self.domains),
            handles=[],
            kind=self.kind,
            country=self.country,
            services=list(self.services),
            register_url=self.register_url,
        )

    def details(self) -> dict[str, object]:
        """Extra facts stored next to the firm row (shown in the firm detail view)."""
        return self.model_dump(
            include={
                "legal_form",
                "former_names",
                "trade_names",
                "former_trade_names",
                "former_domains",
                "address",
                "supervisor",
                "authorized_at",
                "notes",
            }
        )


class RegisterSnapshot(BaseModel):
    """The whole register as saved to `data/fixtures/knf/registry.json`."""

    fetched_at: str
    source_urls: list[str]
    records: list[KnfRecord]


class SyncResult(BaseModel):
    """Outcome of one `registry.sync` run."""

    source: Literal["live", "snapshot"]
    fetched_at: str
    per_kind: dict[str, int]
    total: int
    added: int
    removed: int
    extra_firms: int
    error: str | None = None


class FirmSummary(BaseModel):
    """Row of `GET /api/firms`."""

    firm: RegisteredFirm
    source: FirmSource
    active: bool
    findings: int


class FirmDetail(FirmSummary):
    """`GET /api/firms/{id}`: the firm plus register facts for the UI."""

    supervisor: str | None
    legal_form: str | None
    former_names: list[str]
    trade_names: list[str]
    former_domains: list[str]
    address: str | None
    authorized_at: str | None
    notes: str | None
    synced_at: str


class RegistryStatus(BaseModel):
    """`GET /api/firms/status`: what the "Rejestr" page shows about synchronisation."""

    last_sync: SyncResult | None
    synced_at: str | None
    """When the last sync ran (the snapshot itself may be older: see `last_sync.fetched_at`)."""
    active_per_kind: dict[str, int]
    """Active KNF-register firms per register kind."""
    total_active: int
    fictional: int
    """Active demo/fixture firms (fictional, never from the register)."""
    history: list[SyncResult]
    source_name: str = "Rejestry KNF (Komisja Nadzoru Finansowego)"
    source_url: str = "https://www.knf.gov.pl/podmioty/Podmioty_rynku_kapitalowego"
    legal_basis: str = (
        "informacja sektora publicznego, ponowne wykorzystanie z podaniem źródła i daty "
        "pozyskania (ustawa o otwartych danych, Dz.U. 2021 poz. 1641)"
    )
    attribution: str | None = None
    """Footer text for the UI and reports: "Źródło: rejestry KNF (knf.gov.pl), stan na <date>"."""


class FirmsPage(BaseModel):
    """`GET /api/firms`."""

    total: int
    items: list[FirmSummary]


class SyncQueued(BaseModel):
    """`POST /api/firms/sync`."""

    task_id: str
    live: bool | None


def knf_attribution(fetched_at: str | None) -> str:
    """Source and snapshot date line shown wherever register data is used."""
    date = (fetched_at or "")[:10]
    suffix = f", stan na {date}" if date else ""
    return f"Źródło: rejestry KNF (knf.gov.pl){suffix}"


class KnfWarning(BaseModel):
    """The publisher is on the KNF public warning list (`data/registry/knf_warnings.json`).

    The list has no per-entry date, so `as_of` is the date the snapshot was taken: the entity
    was on the list at least since then.
    """

    name: str
    """The listed entity (one name from a multi-entity row)."""
    method: Literal["domain", "name", "fuzzy"]
    matched_text: str
    """What matched: the post's domain or author name."""
    section: str
    """Statute of the notification (`investment_services`, `banking`, ...)."""
    as_of: str
    """Snapshot date (YYYY-MM-DD)."""
    source_url: str
