"""Celery tasks. Thin wrappers: the logic lives in `pipeline` and `collectors`."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from croniter import croniter

from investwatch.collectors.manual import text_item
from investwatch.collectors.official.youtube_api import YouTubeApiCollector, video_id
from investwatch.collectors.policy import collector_ready
from investwatch.collectors.registry import get_collector
from investwatch.collectors.schemas import CollectedItem
from investwatch.collectors.web import WebCollector
from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.session import session_scope
from investwatch.jobs.celery_app import celery_app
from investwatch.jobs.queues import CHECK_QUEUE, review_queue
from investwatch.pipeline import analyze as pipeline
from investwatch.realtime.emitter import emit_job
from investwatch.realtime.schemas import JobEvent
from investwatch.status.probe import mark_beat_tick

log = logging.getLogger(__name__)


def task_info(task: Any, **extra: Any) -> dict[str, Any]:
    """Celery task id, queue and worker of the running task, for the processing trace."""
    request = task.request
    route = celery_app.conf.task_routes.get(task.name, {})
    delivery = getattr(request, "delivery_info", None) or {}
    return {
        "task": task.name,
        "task_id": request.id,
        "queue": delivery.get("routing_key") or route.get("queue") or "analyze",
        "worker": request.hostname,
        "retries": request.retries or 0,
        **extra,
    }


def _stamp(item: CollectedItem, job: dict[str, Any]) -> CollectedItem:
    """Add the collecting job to the item's raw provenance (`raw.job`)."""
    return item.model_copy(update={"raw": {**(item.raw or {}), "job": job}})


def next_run(cron: str, after: datetime) -> datetime:
    """Return the next time `cron` fires after `after`."""
    nxt: datetime = croniter(cron, after).get_next(datetime)
    return nxt if nxt.tzinfo else nxt.replace(tzinfo=UTC)


@celery_app.task(name="investwatch.analyze_post", bind=True, max_retries=3)
def analyze_post(
    self: Any, post_id: str, job_id: str | None = None, priority: bool = False
) -> dict[str, Any]:
    """Analyse one post; report progress when it belongs to a "check URL" job.

    The model review of a check (`job_id`) or of an analyst submission (`priority`) jumps the
    batch backlog (`llm_priority` queue).
    """
    try:
        outcome = pipeline.analyze_post(uuid.UUID(post_id), task=task_info(self, job_id=job_id))
    except LookupError:
        raise
    except Exception as exc:
        if job_id and self.request.retries >= self.max_retries:
            emit_job(JobEvent(job_id=job_id, stage="failed", error=str(exc)))
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1)) from exc
    if job_id:
        emit_job(
            JobEvent(
                job_id=job_id,
                stage="analyzed",
                post_id=uuid.UUID(post_id),
                finding_ids=[uuid.UUID(f) for f in outcome.finding_ids],
                duplicate_of=uuid.UUID(outcome.duplicate_of) if outcome.duplicate_of else None,
            )
        )
    # The alert is out; the model's second opinion follows from the `llm` queues.
    queue = review_queue(priority or job_id is not None)
    for finding_id in outcome.review_queued:
        review_finding.apply_async((finding_id,), queue=queue)
    return outcome.model_dump()


@celery_app.task(
    name="investwatch.review_finding",
    bind=True,
    soft_time_limit=120,
    time_limit=150,
    max_retries=None,
)
def review_finding(self: Any, finding_id: str) -> dict[str, Any]:
    """LLM second opinion on one finding (`llm_priority` / `llm` queues, concurrency 1).

    When the model is unavailable the finding says so right away and the review is retried a
    few times, so a model that finishes pulling later still gets to answer.
    """
    settings = get_settings()
    try:
        result = pipeline.review_finding(uuid.UUID(finding_id), task=task_info(self))
    except SoftTimeLimitExceeded:
        log.warning("model review of %s hit the task time limit", finding_id)
        return {"finding_id": finding_id, "state": "timeout"}
    if result.state == "unavailable" and self.request.retries < settings.llm_review_max_retries:
        raise self.retry(countdown=settings.llm_review_retry_s)
    return result.model_dump()


@celery_app.task(name="investwatch.embed_missing_posts")
def embed_missing_posts() -> int:
    """Backfill embeddings (and token counts) of posts that never passed the pipeline."""
    return pipeline.embed_missing_posts()


@celery_app.task(name="investwatch.check_url", bind=True, max_retries=2)
def check_url(
    self: Any, job_id: str, url: str | None = None, text: str | None = None
) -> dict[str, Any]:
    """Collect one URL (or pasted text), store it and queue its analysis."""
    if url and video_id(url):  # YouTube: official API by id, never the watch page
        item = YouTubeApiCollector().collect(url)[0]
    else:
        item = WebCollector(name="manual").collect(url)[0] if url else text_item(text or "")
    item = _stamp(item, task_info(self, job_id=job_id))
    with session_scope() as session:
        result = pipeline.ingest_item(session, item)
    post_id = result.post.id
    if result.post.fetch_status != "ok":
        emit_job(
            JobEvent(
                job_id=job_id,
                stage="failed",
                post_id=post_id,
                error=f"fetch_status={result.post.fetch_status}",
            )
        )
        return {"post_id": str(post_id), "fetch_status": result.post.fetch_status}
    emit_job(JobEvent(job_id=job_id, stage="fetched", post_id=post_id))
    analyze_post.apply_async((str(post_id), job_id), queue=CHECK_QUEUE)
    return {"post_id": str(post_id), "fetch_status": "ok"}


@celery_app.task(name="investwatch.scrape_source", bind=True)
def scrape_source(self: Any, source_id: str) -> dict[str, Any]:
    """Run a source's collector and queue analysis of new or changed posts."""
    sid = uuid.UUID(source_id)
    with session_scope() as session:
        source = repo.get_source(session, sid)
        if source is None:
            raise LookupError(f"source {source_id} not found")
        # Never run a source whose connector is not ready (e.g. a removed collector).
        blocked = collector_ready(source.collector, get_settings())
        if blocked is not None:
            log.warning("source %s skipped: %s", source_id, blocked.how_to)
            return {"skipped": blocked.status, "reason": blocked.how_to}
        run_id = repo.start_run(session, sid)
    to_analyze: list[str] = []
    seen = new = 0
    status, error = "ok", None
    try:
        items = get_collector(source.collector).collect(source.target)
        job = task_info(self, run_id=str(run_id), source_id=source_id, cron=source.cron)
        with session_scope() as session:
            for item in items:
                result = pipeline.ingest_item(session, _stamp(item, job), source_id=sid)
                seen += 1
                new += int(result.created)
                if result.changed and result.post.fetch_status == "ok":
                    to_analyze.append(str(result.post.id))
        if items and all(i.fetch_status == "blocked" for i in items):
            status = "blocked"
        elif items and all(i.fetch_status == "error" for i in items):
            status = "error"
        error = next((i.error for i in items if i.error), None)
    except Exception as exc:
        log.exception("source %s failed", source_id)
        status, error = "error", str(exc)
    with session_scope() as session:
        repo.finish_run(session, run_id, status=status, items_new=new, items_seen=seen, error=error)
    for post_id in to_analyze:
        analyze_post.delay(post_id)
    return {"run_id": str(run_id), "status": status, "seen": seen, "new": new}


@celery_app.task(name="investwatch.tick_sources")
def tick_sources() -> list[str]:
    """Queue every due source and schedule its next run from its cron."""
    now = datetime.now(UTC)
    mark_beat_tick(now)
    settings = get_settings()
    queued: list[str] = []
    with session_scope() as session:
        for source in repo.due_sources(session, now):
            repo.update_source(session, source.id, next_run_at=next_run(source.cron, now))
            # A connector without credentials/approval never runs (no fallback to scraping).
            if collector_ready(source.collector, settings) is None:
                queued.append(str(source.id))
    for source_id in queued:
        scrape_source.delay(source_id)
    return queued


@celery_app.task(name="investwatch.sync_registry")
def sync_registry(live: bool | None = None) -> dict[str, Any]:
    """Refresh the KNF register (live, snapshot fallback) and log the sync."""
    from investwatch.registry.sync import sync

    with session_scope() as session:
        return sync(session, live=live).model_dump()


@celery_app.task(name="investwatch.refresh_youtube")
def refresh_youtube() -> dict[str, Any]:
    """Re-read stored YouTube videos (API policy: refresh or delete within 30 days)."""
    if collector_ready("youtube", get_settings()) is not None:
        return {"skipped": "YOUTUBE_API_KEY not set"}
    with session_scope() as session:
        stored = dict((ext, pid) for pid, ext in repo.platform_posts(session, "youtube", "youtube"))
    if not stored:
        return {"refreshed": 0, "removed": 0}
    items, missing = YouTubeApiCollector().refresh(list(stored))
    with session_scope() as session:
        for item in items:
            if item.fetch_status in {"ok", "no_text"}:
                pipeline.ingest_item(session, item)
        for external_id in missing:
            repo.redact_post(session, stored[external_id])
    return {"refreshed": len(items), "removed": len(missing)}
