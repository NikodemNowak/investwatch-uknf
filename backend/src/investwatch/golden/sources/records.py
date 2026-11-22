"""Curated public-data records (`data/golden/public/<source>.jsonl`) and their golden items.

A record is self-contained: text, label and full provenance (source, exact URL, retrieval
date, licence, method). Deleting a source's file removes the source from the set.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from investwatch.core.schemas import ModuleId, Platform
from investwatch.golden.schemas import GoldenItem, GoldenPost, Labeler, Provenance, RuleLabel

log = logging.getLogger(__name__)

PUBLIC_DIR = "public"


class SourceLabel(BaseModel):
    """One line of `data/golden/public/labels/<source>.jsonl` (written by the labeller)."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    module: ModuleId
    label: int | None
    """`None` = looked at and excluded (parked page, off-topic, unreadable); see `note`."""
    rule_labels: dict[str, RuleLabel] = Field(default_factory=dict)
    labeler: Labeler
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = ""
    group: str | None = None
    """Leakage-group override, e.g. `template:<name>` for sites built from one scam template
    (otherwise the source's default: entity or domain)."""


class PublicRecord(BaseModel):
    """One curated, labelled item of a public source."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    module: ModuleId
    label: int
    rule_labels: dict[str, RuleLabel] = Field(default_factory=dict)
    labeler: Labeler
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = ""
    group: str
    """Leakage key: `domain:<host>` or `entity:<id>`; one group never spans both splits."""
    platform: Platform = "web"
    url: str
    author: str
    lang: str | None = None
    text: str
    provenance: Provenance


def domain_group(url: str) -> str:
    """`domain:<host without www>`: the same key the real web items use."""
    host = (urlparse(url).hostname or url).removeprefix("www.")
    return f"domain:{host}"


def item_id(rec: PublicRecord) -> str:
    """Stable, unique golden id of a record."""
    digest = hashlib.sha256(f"{rec.module}|{rec.ref}".encode()).hexdigest()[:10]
    source = rec.provenance.source or "public"
    return f"pub-{rec.module[:2]}-{source}-{digest}"


def load_records(path: Path) -> list[PublicRecord]:
    """Read one source file."""
    return [
        PublicRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save_records(path: Path, records: list[PublicRecord]) -> None:
    """Write one source file, sorted by ref for stable diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r.model_dump_json(exclude_defaults=True) for r in sorted(records, key=lambda r: r.ref)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def to_item(rec: PublicRecord) -> GoldenItem:
    """Golden item of a record, router input computed against the KNF snapshot."""
    from investwatch.golden.real import _post, registry_firms
    from investwatch.registry.match import match_firms, register_status

    row = {
        "platform": rec.platform,
        "collector": rec.provenance.collector,
        "external_id": rec.ref,
        "url": rec.url,
        "author": rec.author,
        "text": rec.text,
        "lang": rec.lang,
    }
    matches = match_firms(_post(row), list(registry_firms()))
    return GoldenItem(
        id=item_id(rec),
        module=rec.module,
        label=1 if rec.label else 0,
        rule_labels=rec.rule_labels,
        origin="real",
        provenance=rec.provenance,
        group=rec.group,
        post=GoldenPost(
            platform=rec.platform,
            collector=rec.provenance.collector,
            external_id=rec.ref,
            url=rec.url,
            author=rec.author,
            text=rec.text,
            lang=rec.lang,
        ),
        firm_matches=matches[:5],
        register_status=register_status(matches),
        labeler=rec.labeler,
        confidence=rec.confidence,
        note=rec.note,
    )


def public_items(root: Path) -> list[GoldenItem]:
    """Golden items of every committed source file under `data/golden/public/`."""
    folder = root / PUBLIC_DIR
    if not folder.exists():
        return []
    items: list[GoldenItem] = []
    for path in sorted(folder.glob("*.jsonl")):
        recs = load_records(path)
        items.extend(to_item(r) for r in recs)
        log.info("%s: %d items", path.name, len(recs))
    return items
