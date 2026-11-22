"""Shape of one golden-set item (`data/golden/golden.jsonl`).

The AI service reads the same file with its own copy of this module
(`ai/src/investwatch_ai/eval/golden.py`, identical except for the contract import; a test in
`ai/tests/test_eval.py` checks it). Labelling rules: `docs/eval/LABELING.md`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from investwatch.core.schemas import FirmMatch, ModuleId, Platform

Origin = Literal["synthetic", "real"]
Split = Literal["train", "holdout"]
Labeler = Literal["generator", "model", "agent", "human", "rule"]
"""Who produced the label: built by construction, an LLM, an AI agent reading it, a person,
or a documented rule over an official source (e.g. the KNF warning list; see `note`)."""
RuleLabel = Literal["pass", "fail", "na"]
RegisterStatus = Literal["registered", "registered_without_advice", "not_registered"]


class GoldenPost(BaseModel):
    """The publication itself; `text` is empty for real posts (resolved from `raw/`)."""

    model_config = ConfigDict(extra="forbid")

    platform: Platform
    collector: str
    external_id: str
    url: str
    author: str
    author_url: str | None = None
    text: str = ""
    lang: str | None = "pl"


AcquisitionMethod = Literal[
    "generator",
    "demo_site",
    "manual",
    "official_api",
    "http_robots_respecting",
    "yt_dlp",
    "meta_ad_library_page",
    "tiktok_page",
    "official_list",
    "web_archive",
    "open_dataset",
]
"""How the content was obtained.

`generator`: built by `golden/synth.py`; `demo_site`: our own pages in `demo-sites/`;
`manual`: supplied by a team member (pasted or uploaded, with the source noted);
`official_api`: a platform API used within its terms; `http_robots_respecting`: public web
pages fetched by the `web` collector honouring robots.txt. The last three were collected
outside an official API and are under compliance review: never part of headline metrics.
`official_list`: a regulator's published list; `web_archive`: a public Internet Archive
snapshot via its documented API; `open_dataset`: a published dataset under an open licence.
Sources, licences and legal basis: `docs/eval/DATA_SOURCES.md`.
"""
SCRAPED_SOCIAL: frozenset[str] = frozenset({"yt_dlp", "meta_ad_library_page", "tiktok_page"})
"""Methods excluded by `--exclude-scraped` (platform pages fetched outside an official API)."""


class Provenance(BaseModel):
    """Where an item comes from, so non-compliant sources can be dropped with one filter."""

    model_config = ConfigDict(extra="forbid")

    collector: str
    method: AcquisitionMethod
    compliant: Literal["yes", "no", "under_review"]
    source: str | None = None
    """Public-data source id (`golden/sources/`), e.g. `knf_warnings_wayback`."""
    source_url: str | None = None
    """Exact URL the content was retrieved from (e.g. the Wayback snapshot)."""
    retrieved_at: str | None = None
    licence: str | None = None

    @property
    def headline(self) -> bool:
        """May this item count towards the headline (reported) metrics?"""
        return self.method not in SCRAPED_SOCIAL and self.compliant == "yes"


class Review(BaseModel):
    """A human confirmation of the label (held-out items must have one before reporting)."""

    model_config = ConfigDict(extra="forbid")

    by: str
    at: str
    decision: Literal["accepted", "changed", "excluded"]
    previous_label: int | None = None


class GoldenItem(BaseModel):
    """One labelled item: the module it tests, the verdict and, for M2, per-rule verdicts."""

    model_config = ConfigDict(extra="forbid")

    id: str
    module: ModuleId
    label: Literal[0, 1]
    """1 = violation / positive for the module (M1 third-party promo, M2 breach, M3 advice)."""
    rule_labels: dict[str, RuleLabel] = Field(default_factory=dict)
    """Only rules whose verdict is known; absent rules are not scored."""
    origin: Origin
    provenance: Provenance
    split: Split = "train"
    group: str
    """Leakage key (firm, domain or author): one group never spans both splits."""
    post: GoldenPost
    text_ref: str | None = None
    """`raw/posts.jsonl#<platform>:<external_id>` for real posts."""
    render_path: str | None = None
    """RenderSnapshot JSON relative to `data/golden/` (synthetic pages)."""
    html_path: str | None = None
    firm_matches: list[FirmMatch] = Field(default_factory=list)
    """Router input frozen at build time (registry snapshot + fictional firms)."""
    register_status: RegisterStatus | None = None
    labeler: Labeler
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = ""
    review: Review | None = None

    @property
    def excluded(self) -> bool:
        """A reviewer removed the item (unusable, ambiguous or off-topic)."""
        return self.review is not None and self.review.decision == "excluded"
