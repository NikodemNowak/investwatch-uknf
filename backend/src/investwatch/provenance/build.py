"""Assemble the "Pod maską" view from the post row, its trace and its stored objects."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.schemas import FindingView
from investwatch.provenance.schemas import (
    CollectJob,
    FetchInfo,
    ModelParts,
    ObjectKind,
    SimilarPost,
    SourceInfo,
    StoredObject,
    UnderTheHood,
)
from investwatch.storage.minio import get_store

log = logging.getLogger(__name__)


def model_parts(model: str) -> ModelParts:
    """Split `Finding.model` (`[mock+][llm+]rules-vN[+lr-vN-variant]`) into its parts."""
    parts = model.split("+")
    # The backend's offline fallback names itself `mock-rules-v0`.
    out = ModelParts(mock=parts[0].startswith("mock"))
    for part in parts:
        if part == "mock":
            continue
        if "rules-" in part:
            out.rules_version = part
        elif part.startswith("lr-"):
            version, _, variant = part.rpartition("-")
            out.classifier, out.classifier_variant = version, variant
        else:
            out.llm_model = part
    return out


def classifier_note(explanation: str) -> str | None:
    """The `Klasyfikator (...): p = ...` sentence the `ai` service appends, if any."""
    start = explanation.find("Klasyfikator (")
    if start < 0:
        return None
    # Decimals ("p = 0.83") never have a space after the dot; the sentence end does.
    end = explanation.find(". ", start)
    return explanation[start : end + 1 if end >= 0 else None].strip()


def _object(kind: ObjectKind, label: str, key: str, content_type: str) -> StoredObject:
    bucket = get_settings().minio_bucket
    try:
        found = get_store().describe(key)
    except Exception:  # storage down: list the key, without size and hash
        log.exception("cannot read %s", key)
        found = None
    return StoredObject(
        kind=kind,
        label=label,
        key=key,
        bucket=bucket,
        content_type=content_type,
        bytes=found[0] if found else None,
        sha256=found[1] if found else None,
    )


def _raw(post_id: uuid.UUID) -> dict[str, Any] | None:
    try:
        data = get_store().get_bytes(f"raw/{post_id}.json")
        loaded = json.loads(data) if data else None
    except Exception:
        log.exception("cannot read the raw envelope of %s", post_id)
        return None
    return loaded if isinstance(loaded, dict) else None


def _fetch(raw: dict[str, Any]) -> FetchInfo | None:
    fetch = raw.get("fetch") if isinstance(raw.get("fetch"), dict) else {}
    try:
        return FetchInfo.model_validate(
            {**{k: v for k, v in raw.items() if k in FetchInfo.model_fields}, **(fetch or {})}
        )
    except ValidationError:
        log.warning("malformed raw envelope", exc_info=True)
        return None


def _job(raw: dict[str, Any]) -> CollectJob | None:
    job = raw.get("job")
    if not isinstance(job, dict):
        return None
    try:
        return CollectJob.model_validate(job)
    except ValidationError:
        return None


def under_the_hood(session: Session, finding: FindingView) -> UnderTheHood:
    """Provenance and processing trace of one finding's material."""
    post = finding.post
    row = repo.post_row(session, post.id)
    source = repo.get_source(session, row.source_id) if row and row.source_id else None
    raw = _raw(post.id)
    raw_key = f"raw/{post.id}.json"
    objects: list[StoredObject] = []
    if post.html_key and post.html_key != raw_key:
        objects.append(_object("html", "html", post.html_key, "text/html"))
    if raw is not None:
        objects.append(_object("raw", "raw", raw_key, "application/json"))
    if post.render_key:
        objects.append(_object("render", "render", post.render_key, "application/json"))
    for viewport, key in post.screenshot_keys.items():
        objects.append(_object("screenshot", viewport, key, "image/png"))
    similar = repo.similar_posts(session, post.id)
    return UnderTheHood(
        finding_id=finding.id,
        post_id=post.id,
        content_hash=post.content_hash,
        render_hash=row.render_hash if row else None,
        tokens=(row.token_count if row else None)
        or (finding.trace.tokens if finding.trace else None),
        source=SourceInfo(
            id=source.id,
            name=source.name,
            collector=source.collector,
            cron=source.cron,
            next_run_at=source.next_run_at,
            last_run_at=source.last_run_at,
        )
        if source
        else None,
        collect_job=_job(raw) if raw else None,
        fetch=_fetch(raw) if raw else None,
        objects=objects,
        trace=finding.trace,
        model=model_parts(finding.model),
        classifier_note=classifier_note(finding.explanation),
        similar=[
            SimilarPost(
                post_id=p.id,
                url=p.url,
                author=p.author,
                similarity=round(sim, 4),
                finding_id=fid,
            )
            for p, sim, fid in similar
        ],
        similar_available=bool(similar)
        or (
            session.get_bind().dialect.name == "postgresql"
            and row is not None
            and row.embedding is not None
        ),
    )
