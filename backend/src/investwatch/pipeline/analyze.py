"""Ingest and analysis pipeline.

store -> dedup -> register match -> AI fast pass (rules, embedding) -> save -> alert
-> `llm` queue: model second opinion -> update finding -> `finding_updated` (+ late alert).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from investwatch.collectors.schemas import CollectedItem
from investwatch.config import get_settings
from investwatch.core.schemas import Alert, Finding, Post, RenderSnapshot
from investwatch.db import repo
from investwatch.db.schemas import LlmTrace, ProcessingTrace, TaskTrace, UpsertResult
from investwatch.db.session import session_scope
from investwatch.pipeline import ai_client
from investwatch.pipeline.dedup import render_hash, to_post
from investwatch.pipeline.schemas import AnalysisOutcome, AnalyzeResponse, ReviewResult
from investwatch.provenance.build import model_parts
from investwatch.realtime.emitter import emit_alert, emit_finding_updated
from investwatch.registry.match import match_firms, register_status
from investwatch.registry.schemas import KnfWarning
from investwatch.registry.warnings import match_warning
from investwatch.storage.minio import get_store

log = logging.getLogger(__name__)

EMBED_MAX_CHARS = 8000
"""Same cut as the `ai` service's fast pass."""


def ingest_item(
    session: Session, item: CollectedItem, source_id: uuid.UUID | None = None
) -> UpsertResult:
    """Upsert a collected item as a post and put its artefacts in object storage."""
    result = repo.upsert_post(session, to_post(item), source_id)
    post_id = result.post.id
    store = get_store()
    html_key = render_key = None
    if item.html and result.changed:
        html_key = store.put_bytes(f"raw/{post_id}.html", item.html.encode(), "text/html")
    if item.raw is not None and result.changed:
        # Platform collectors have no HTML; their source JSON is the raw artefact instead.
        raw_json = json.dumps(item.raw, ensure_ascii=False, default=str).encode()
        raw_key = store.put_bytes(f"raw/{post_id}.json", raw_json, "application/json")
        html_key = html_key or raw_key
    if item.render is not None:
        render_key = store.put_bytes(
            f"render/{post_id}.json", item.render.model_dump_json().encode(), "application/json"
        )
    shot_keys = {
        str(viewport): store.put_bytes(f"shots/{post_id}/{viewport}.png", png, "image/png")
        for viewport, png in item.screenshots.items()
    }
    layout = render_hash(item.render)
    if html_key or render_key or shot_keys or layout:
        repo.set_post_keys(
            session,
            post_id,
            html_key=html_key,
            render_key=render_key,
            screenshot_keys=shot_keys,
            render_hash=layout,
        )
        post = repo.get_post(session, post_id)
        assert post is not None
        result = result.model_copy(update={"post": post})
    return result


def _load_render(post: Post) -> RenderSnapshot | None:
    if not post.render_key:
        return None
    try:
        data = get_store().get_bytes(post.render_key)
        return RenderSnapshot.model_validate_json(data) if data else None
    except Exception:
        log.exception("cannot load render snapshot %s", post.render_key)
        return None


def analyze_post(post_id: uuid.UUID, task: dict[str, Any] | None = None) -> AnalysisOutcome:
    """Analyse one stored post and emit alerts for findings above the module threshold."""
    settings = get_settings()
    with session_scope() as session:
        post = repo.get_post(session, post_id)
        if post is None:
            raise LookupError(f"post {post_id} not found")
        if post.fetch_status != "ok" or not post.text.strip():
            return AnalysisOutcome(post_id=str(post_id), analyzer="skipped")
        # Same text and same layout: join the original's occurrence group, keep this location.
        original = repo.find_hash_duplicate(session, post_id)
        if original is not None:
            repo.mark_duplicate(session, post_id, original)
            return AnalysisOutcome(
                post_id=str(post_id), duplicate_of=str(original), analyzer="skipped"
            )
        matches = match_firms(post, repo.list_firms(session))
        status = register_status(matches)
        thresholds = repo.get_thresholds(session)
    warning = _warning(post, status)

    # Keep the AI call outside any DB transaction.
    response, analyzer = ai_client.analyze(
        post,
        _load_render(post),
        matches,
        thresholds.as_dict(),
        register_status=status,
        knf_warning=warning.name if warning else None,
    )

    with session_scope() as session:
        trace = _trace(response, analyzer)
        if task is not None:
            trace.task = TaskTrace.model_validate(task)
        repo.set_trace(session, post_id, trace, response.tokens)
        if response.embedding:
            near = repo.find_near_duplicate(
                session, post_id, response.embedding, settings.near_duplicate_cosine
            )
            repo.set_embedding(session, post_id, response.embedding)
            if near is not None:
                repo.mark_duplicate(session, post_id, near)
                return AnalysisOutcome(
                    post_id=str(post_id), duplicate_of=str(near), analyzer=analyzer
                )
        findings = [f.model_copy(update={"post_id": post_id}) for f in response.findings]
        saved = repo.save_findings(session, findings)
        repo.set_knf_warning(session, post_id, warning)

    alerted: list[str] = []
    for finding in saved:
        if finding.status == "new" and finding.score >= thresholds.for_module(finding.module):
            emit_alert(Alert(finding=finding, post=post))
            alerted.append(str(finding.id))
    queued = [str(f.id) for f in saved if f.llm_review == "queued"]
    log.info(
        "analysed post %s with %s: %d findings, %d alerts, %d queued for the model",
        post_id,
        analyzer,
        len(saved),
        len(alerted),
        len(queued),
    )
    return AnalysisOutcome(
        post_id=str(post_id),
        finding_ids=[str(f.id) for f in saved],
        alerted=alerted,
        review_queued=queued,
        analyzer=analyzer,
    )


def _warning(post: Post, status: str) -> KnfWarning | None:
    """Warning-list entity that published the post; names only for unregistered publishers."""
    try:
        return match_warning(post, by_name=status == "not_registered")
    except Exception:  # a broken snapshot must not stop the analysis
        log.exception("KNF warning-list match failed for post %s", post.id)
        return None


def _trace(response: AnalyzeResponse, analyzer: str) -> ProcessingTrace:
    # `model` ends with the classifier head when one scored the finding; find the rules part.
    rules_version = (
        model_parts(response.findings[0].model).rules_version if response.findings else None
    )
    return ProcessingTrace(
        analyzer=analyzer,
        analyzed_at=datetime.now(UTC),
        chars=response.chars,
        tokens=response.tokens,
        embed_model=response.embed_model,
        embedding_dim=len(response.embedding) if response.embedding else None,
        lang=response.lang,
        rules_version=rules_version,
        timings_ms=response.timings_ms,
    )


def _changed_rules(before: Finding, after: Finding) -> list[str]:
    old = {r.rule_id: r.status for r in before.rules}
    return [r.rule_id for r in after.rules if old.get(r.rule_id) != r.status]


def review_finding(finding_id: uuid.UUID, task: dict[str, Any] | None = None) -> ReviewResult:
    """Ask the model for its second opinion on a finding and store the result.

    Rule results, score and alert from the fast pass stand until the model answers. When it
    cannot (Ollama down, model still pulling, 90 s budget spent) the finding is marked
    `unavailable` at once, so the UI says so; the caller may retry later.
    """
    settings = get_settings()
    with session_scope() as session:
        current = repo.get_finding(session, finding_id)
        if current is None:
            raise LookupError(f"finding {finding_id} not found")
        if current.llm_review not in ("queued", "unavailable"):
            return ReviewResult(finding_id=str(finding_id), state="skipped")
        post = current.post
        matches = match_firms(post, repo.list_firms(session))
        status = register_status(matches)
        thresholds = repo.get_thresholds(session)
        trace = repo.get_trace(session, post.id)

    response, analyzer = ai_client.analyze(
        post,
        _load_render(post),
        matches,
        thresholds.as_dict(),
        register_status=status,
        llm_pass=True,
        knf_warning=current.knf_warning.name if current.knf_warning else None,
    )
    reviewed = next((f for f in response.findings if f.module == current.module), None)
    if analyzer != "ai" or reviewed is None or reviewed.llm_review != "done":
        state = "unavailable"
        error = response.llm_error or (
            "ai service unreachable" if analyzer != "ai" else "no model verdict"
        )
        updated: Finding = current.model_copy(update={"llm_review": state})
    else:
        state, error = "done", None
        updated = reviewed.model_copy(
            update={"id": current.id, "post_id": post.id, "status": current.status}
        )

    with session_scope() as session:
        repo.save_findings(session, [_contract(updated)])
        if trace is not None:
            usage = response.llm
            trace.llm = LlmTrace(
                state=state,
                model=usage.model if usage else settings.llm_model,
                prompt_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                ms=usage.ms if usage else None,
                error=error,
                finished_at=datetime.now(UTC),
                task=TaskTrace.model_validate(task) if task is not None else None,
            )
            repo.set_trace(session, post.id, trace)
        view = repo.get_finding(session, finding_id)
    assert view is not None

    emit_finding_updated(view)
    threshold = thresholds.for_module(view.module)
    alerted = view.status == "new" and view.score >= threshold and current.score < threshold
    if alerted:
        emit_alert(Alert(finding=_contract(view), post=post))
    changed = _changed_rules(current, view)
    log.info(
        "model review of finding %s: %s, changed rules %s%s",
        finding_id,
        state,
        changed,
        " (late alert)" if alerted else "",
    )
    return ReviewResult(
        finding_id=str(finding_id), state=state, changed_rules=changed, alerted=alerted
    )


def _contract(finding: Finding) -> Finding:
    """Strip read-model extras (inlined post, trace) from a `FindingView`."""
    return Finding.model_validate(finding.model_dump(include=set(Finding.model_fields)))


def embed_missing_posts(limit: int | None = None) -> int:
    """Embed posts that never passed the pipeline (seeded fixtures); returns how many.

    One post per request so each gets its own token count. Stops at the first failure:
    Ollama is down or still pulling bge-m3, and Beat will call again.
    """
    settings = get_settings()
    with session_scope() as session:
        posts = repo.posts_without_embedding(session, limit or settings.embed_backfill_batch)
    done = 0
    for post in posts:
        out = ai_client.embed([post.text[:EMBED_MAX_CHARS]])
        if out is None or not out.embeddings:
            break
        with session_scope() as session:
            repo.set_embedding(session, post.id, out.embeddings[0])
            if out.tokens is not None:
                repo.set_token_count(session, post.id, out.tokens)
        done += 1
    if done:
        log.info("embedded %d stored posts", done)
    return done
