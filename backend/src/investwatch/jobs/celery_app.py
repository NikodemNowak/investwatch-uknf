"""Celery application: `check`, `scrape`, `analyze`, `llm_priority`, `llm`, `maintenance`.

`llm` holds the model's second opinion: one slow task at a time, so a CPU-only
machine still gets alerts from `analyze` in seconds. `llm_priority` holds the reviews of
material an analyst submitted and is drained first; `check` runs that material's fetch and
rules analysis on its own worker (`investwatch.jobs.queues`).
"""

from __future__ import annotations

from celery import Celery

from investwatch.config import get_settings
from investwatch.jobs.beat import BEAT_SCHEDULE
from investwatch.jobs.queues import CHECK_QUEUE, LLM_QUEUE


def create_app() -> Celery:
    """Build the Celery app from settings."""
    settings = get_settings()
    app = Celery(
        "investwatch",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["investwatch.jobs.tasks"],
    )
    app.conf.update(
        task_always_eager=settings.celery_eager,
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=24 * 3600,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"queue_order_strategy": settings.celery_queue_order},
        task_default_queue="analyze",
        task_routes={
            "investwatch.scrape_source": {"queue": "scrape"},
            "investwatch.check_url": {"queue": CHECK_QUEUE},
            "investwatch.analyze_post": {"queue": "analyze"},
            "investwatch.review_finding": {"queue": LLM_QUEUE},
            "investwatch.tick_sources": {"queue": "maintenance"},
            "investwatch.sync_registry": {"queue": "maintenance"},
            "investwatch.embed_missing_posts": {"queue": "maintenance"},
        },
        beat_schedule=BEAT_SCHEDULE,
        timezone="UTC",
    )
    return app


celery_app = create_app()
