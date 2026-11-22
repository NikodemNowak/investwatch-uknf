"""Shared data contract (plan section 3.12).

A verbatim copy lives in `ai/src/investwatch_ai/schemas.py`; CI checks that both stay equal.
Field names are part of the public API: change them only in a `feat(contract)` PR.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["web", "facebook", "instagram", "tiktok", "youtube", "bing", "sample"]
ModuleId = Literal["m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory"]
Status = Literal["new", "in_review", "confirmed", "dismissed"]
RiskLevel = Literal["low", "medium", "high"]
RuleStatus = Literal["pass", "fail", "na", "unknown"]
CheckType = Literal["text", "render", "llm"]
Viewport = Literal["desktop", "tablet", "phone"]
FetchStatus = Literal["ok", "blocked", "error", "no_text"]
FirmKind = Literal[
    "dom_maklerski", "bank_maklerski", "oddzial_zagraniczny", "zagraniczna_bez_oddzialu"
]
TrendBucket = Literal["hour", "day", "week"]
LlmReviewState = Literal["none", "queued", "done", "unavailable"]
"""Model second opinion on a finding: not needed / waiting in the `llm` queue / merged /
Ollama or the model could not answer (rule results stand)."""

BBox = tuple[float, float, float, float]
"""x, y, width, height in CSS pixels of the full page."""

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ContractModel(BaseModel):
    """Base for contract models: unknown fields are an error, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class PostProvenance(ContractModel):
    """How a post was obtained (ADR 0008), shown next to it in the UI."""

    access_mode: str
    """`official_api`, `open_dataset`, `file_import`, `analyst` or `crawler`."""
    legal_basis: str | None = None
    fetched_at: datetime | None = None
    synthetic: bool = False
    """Fictional demo material (synthetic fixtures, fictional firms' pages)."""
    note: str | None = None
    """The importer's provenance note, when the post came from a file."""
    fetch_error: str | None = None
    """Why the source could not be read (robots.txt refusal, 403, throttling), if it failed."""


class Post(ContractModel):
    """One collected publication (web page, social post, video description)."""

    id: UUID
    platform: Platform
    collector: str
    """"web", "meta_ad_library", "tiktok_ccl", "youtube", "sample" or "manual"."""
    external_id: str
    url: str
    canonical_url: str
    author: str
    """Handle, page name or domain."""
    author_url: str | None
    text: str
    """Cleaned text."""
    lang: str | None
    content_hash: str
    html_key: str | None
    render_key: str | None
    """Object key of the RenderSnapshot in MinIO."""
    screenshot_keys: dict[Viewport, str]
    published_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    fetch_status: FetchStatus = "ok"
    provenance: PostProvenance | None = None


class TextBlock(ContractModel):
    """One rendered element with its own text, as measured in the browser."""

    text: str
    bbox: BBox
    font_px: float
    font_weight: int
    color: str
    """"#rrggbb"."""
    background: str
    """First non-transparent background up the tree, "#rrggbb"."""
    opacity: Probability
    visible: bool
    occluded: bool
    clipped: bool
    in_footer: bool
    in_collapsed: bool
    y_ratio: float
    """Vertical position divided by page height."""
    tag_path: str


class RenderSnapshot(ContractModel):
    """Layout facts for one page in each viewport (rules 4-8, 13)."""

    viewports: dict[Viewport, list[TextBlock]]
    page_height: dict[Viewport, float]


class RegisteredFirm(ContractModel):
    """Investment firm from one of the KNF registers."""

    id: UUID
    name: str
    aliases: list[str]
    domains: list[str]
    handles: list[str]
    kind: FirmKind
    country: str | None
    services: list[str]
    """MiFID II Annex I codes, e.g. ["A1", "A5"]."""
    register_url: str
    fictional: bool = False
    """A fictional firm added for the demo (not in any KNF register)."""


class FirmMatch(ContractModel):
    """Evidence that a post is by or about a registered firm."""

    firm: RegisteredFirm
    confidence: Probability
    method: Literal["domain", "handle", "alias", "fuzzy"]
    matched_text: str
    on: Literal["author", "content"]


class Evidence(ContractModel):
    """A quote and/or a measured region backing a rule result."""

    quote: str | None
    viewport: Viewport | None
    bbox: BBox | None
    measurements: dict[str, float | str]
    """E.g. {"risk_font_px": 9, "dominant_font_px": 16, "ratio": 0.56}."""


class RuleResult(ContractModel):
    """Outcome of one rule ("1".."18", "12a", "12b", or "76a".."76e" for M3)."""

    rule_id: str
    name: str
    status: RuleStatus
    confidence: Probability
    check_type: CheckType
    weight: Probability
    explanation: str
    """In Polish."""
    legal_basis: str
    evidence: list[Evidence]


class Finding(ContractModel):
    """Result of one module for one post."""

    id: UUID
    post_id: UUID
    module: ModuleId
    score: Probability
    risk_level: RiskLevel
    explanation: str
    quotes: list[str]
    firm: RegisteredFirm | None
    firm_match: FirmMatch | None
    advertiser: str | None
    """M1: the third party; M3: the unauthorised entity."""
    rules: list[RuleResult]
    """M2: all rules; M1: a subset; M3: art. 76 elements "76a".."76e"."""
    model: str
    """E.g. "bielik-11b-v3.1+rules-v1"."""
    used_llm: bool
    llm_review: LlmReviewState = "none"
    duplicates: int = 0
    status: Status = "new"
    created_at: datetime


class Alert(ContractModel):
    """Socket.IO `alert` event payload."""

    finding: Finding
    post: Post


class CalibrationPoint(ContractModel):
    """Confusion matrix and metrics at one threshold."""

    threshold: Probability
    tp: int
    fp: int
    fn: int
    tn: int
    precision: Probability
    recall: Probability
    f1: Probability
    f2: Probability


class HistogramBin(ContractModel):
    """Score histogram bin [lo, hi) over all findings, split by label where known."""

    lo: Probability
    hi: Probability
    count: int
    positives: int
    negatives: int


class CalibrationReport(ContractModel):
    """Response of `GET /api/calibration/{module}`."""

    module: ModuleId
    n_labels: int
    n_positive: int
    current_threshold: Probability
    recommended_f1: Probability
    """Threshold with the highest F1 (the current threshold while there are no labels)."""
    recommended_f2: Probability
    points: list[CalibrationPoint]
    """Thresholds 0.00-1.00 in steps of 0.01."""
    histogram: list[HistogramBin]
    min_labels: int = 20
    """Below this many labels the curve is not trustworthy: show an empty state instead."""
    labels_by_source: dict[str, int] = Field(default_factory=dict)
    """Label counts per source: `golden` (golden set) and `analyst` (record status changes)."""


class TrendPoint(ContractModel):
    """Findings created in one bucket for one module."""

    bucket_start: date
    bucket_at: datetime | None = None
    """Start of the bucket (UTC); set for hourly buckets, where `bucket_start` is only the day."""
    module: ModuleId
    total: int
    high: int
    medium: int
    low: int


class TrendSeries(ContractModel):
    """Response of `GET /api/stats/trend`."""

    bucket: TrendBucket
    start: date
    end: date
    points: list[TrendPoint]
