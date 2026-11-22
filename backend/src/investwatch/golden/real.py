"""Real part of the golden set: collected public posts + labels from `labels/real.jsonl`.

Texts stay in `raw/posts.jsonl` (referenced, not copied). Router input (firm matches and the
publisher's register status) is computed once here with the production matcher against the
committed KNF snapshot, so the evaluation does not need the database.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from investwatch.config import get_settings
from investwatch.core.schemas import ModuleId, Post, RegisteredFirm
from investwatch.golden.schemas import GoldenItem, GoldenPost, Labeler, Provenance
from investwatch.pipeline.dedup import canonical_url, content_hash
from investwatch.registry import knf
from investwatch.registry.match import match_firms, register_status
from investwatch.registry.sync import BRANDS_FILE, SNAPSHOT_FILE, apply_brands, load_extra_firms

log = logging.getLogger(__name__)

RAW_FILE = "raw/posts.jsonl"
LABELS_FILE = "labels/real.jsonl"

PROVENANCE: dict[str, Provenance] = {
    "web": Provenance(collector="web", method="http_robots_respecting", compliant="yes"),
    "youtube": Provenance(collector="youtube", method="yt_dlp", compliant="under_review"),
    "meta_ad_library": Provenance(
        collector="meta_ad_library", method="meta_ad_library_page", compliant="under_review"
    ),
    "tiktok": Provenance(collector="tiktok", method="tiktok_page", compliant="under_review"),
}


class RealLabel(BaseModel):
    """One line of `labels/real.jsonl`."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    """`<platform>:<external_id>` of the raw post."""
    module: ModuleId
    label: int
    labeler: Labeler
    confidence: float
    note: str = ""


def raw_ref(row: dict[str, Any]) -> str:
    """Key of a raw post."""
    return f"{row['platform']}:{row['external_id']}"


def load_raw(root: Path) -> dict[str, dict[str, Any]]:
    """Raw collected posts keyed by `raw_ref` (first occurrence wins)."""
    out: dict[str, dict[str, Any]] = {}
    path = root / RAW_FILE
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out.setdefault(raw_ref(row), row)
    return out


@cache
def registry_firms() -> tuple[RegisteredFirm, ...]:
    """KNF snapshot with curated brands, plus the fictional demo firms."""
    settings = get_settings()
    snapshot = knf.load_snapshot(settings.registry_dir / SNAPSHOT_FILE)
    records = apply_brands(snapshot.records, settings.registry_dir / BRANDS_FILE)
    extra = load_extra_firms(settings.registry_extra_paths)
    return (*(r.to_firm() for r in records), *extra)


def _group(row: dict[str, Any]) -> str:
    if row["platform"] == "web":
        host = urlparse(row["url"]).hostname or row.get("author") or ""
        return f"domain:{host.removeprefix('www.')}"
    # Rows reduced to an id (ADR 0008) may have lost the author: fall back to the post itself.
    author = (row.get("author") or "").strip().lower()
    return f"author:{author}" if author else f"post:{raw_ref(row)}"


def _post(row: dict[str, Any]) -> Post:
    now = datetime.now(UTC)
    text = row.get("text") or ""
    return Post(
        id=uuid.uuid4(),
        platform=row["platform"],
        collector=row["collector"],
        external_id=row["external_id"],
        url=row["url"],
        canonical_url=canonical_url(row["url"]),
        author=row.get("author") or "",
        author_url=row.get("author_url"),
        text=text,
        lang=row.get("lang"),
        content_hash=content_hash(text),
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=None,
        first_seen_at=now,
        last_seen_at=now,
    )


def real_items(root: Path) -> list[GoldenItem]:
    """Golden items for every labelled raw post."""
    labels_path = root / LABELS_FILE
    if not labels_path.exists():
        return []
    raw = load_raw(root)
    firms = list(registry_firms())
    items: list[GoldenItem] = []
    skipped = 0
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        lab = RealLabel.model_validate_json(line)
        row = raw.get(lab.ref)
        if row is None:
            # The raw post was withdrawn (e.g. a compliance clean-up): drop its label too.
            log.info("skip %s: not in %s", lab.ref, RAW_FILE)
            skipped += 1
            continue
        note = lab.note
        if not (row.get("text") or "").strip():
            note = f"{note} [no text: needs an official API fetch]".strip()
        matches = match_firms(_post(row), firms)
        items.append(
            GoldenItem(
                id=f"real-{lab.module[:2]}-{lab.ref.replace(':', '-')}"[:80],
                module=lab.module,
                label=1 if lab.label else 0,
                origin="real",
                provenance=PROVENANCE.get(
                    row["collector"],
                    Provenance(
                        collector=row["collector"], method="manual", compliant="under_review"
                    ),
                ),
                group=_group(row),
                post=GoldenPost(
                    platform=row["platform"],
                    collector=row["collector"],
                    external_id=row["external_id"],
                    url=row["url"],
                    author=row.get("author") or "",
                    author_url=row.get("author_url"),
                    lang=row.get("lang"),
                ),
                text_ref=f"{RAW_FILE}#{lab.ref}",
                firm_matches=matches[:5],
                register_status=register_status(matches),
                labeler=lab.labeler,
                confidence=lab.confidence,
                note=note,
            )
        )
    if skipped:
        log.warning("%d labelled raw posts are missing from %s", skipped, RAW_FILE)
    return items


def resolve_text(root: Path, item: GoldenItem) -> str:
    """The item's text: inline for synthetic items, from `raw/posts.jsonl` for real ones."""
    if item.post.text or not item.text_ref:
        return item.post.text
    _, _, ref = item.text_ref.partition("#")
    row = _raw_cached(str(root)).get(ref)
    return str(row.get("text") or "") if row else ""


@cache
def _raw_cached(root: str) -> dict[str, dict[str, Any]]:
    return load_raw(Path(root))
