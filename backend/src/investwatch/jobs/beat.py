"""Celery Beat schedule: one tick per minute; per-source cron lives in the `sources` table."""

from __future__ import annotations

from typing import Any

from celery.schedules import crontab

BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "tick-sources": {"task": "investwatch.tick_sources", "schedule": 60.0},
    # Daily, off-peak; the task falls back to the committed snapshot when knf.gov.pl is down.
    "sync-knf-registry": {
        "task": "investwatch.sync_registry",
        "schedule": crontab(hour=4, minute=17),
    },
    # Seeded posts never pass the pipeline; a no-op once every post has its vector.
    "embed-missing-posts": {"task": "investwatch.embed_missing_posts", "schedule": 120.0},
    # YouTube API policy: stored API data is refreshed (or deleted) at least every 30 days.
    "refresh-youtube": {
        "task": "investwatch.refresh_youtube",
        "schedule": crontab(day_of_week=1, hour=5, minute=11),
    },
}
