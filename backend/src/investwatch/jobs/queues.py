"""Queues for analyst-initiated work, and where a model review waits.

Material an analyst submitted ("Sprawdź", "Zgłoś materiał") never queues behind batch work:
- its fetch/render and rules analysis run on `check`, served only by `worker-check` (scrape
  and analyze workers can be busy with a source crawl for minutes);
- its model review goes to `llm_priority`; `worker-llm` consumes `llm_priority,llm` in that
  fixed order (`CELERY_QUEUE_ORDER=priority`), so it waits at most for the one review that is
  already running, never for the whole backlog.
Everything else (sources, imports, the demo replay) uses `scrape`, `analyze` and `llm`.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

import redis
from pydantic import BaseModel

from investwatch.config import get_settings

log = logging.getLogger(__name__)

CHECK_QUEUE = "check"
LLM_QUEUE = "llm"
LLM_PRIORITY_QUEUE = "llm_priority"
LLM_QUEUES = (LLM_PRIORITY_QUEUE, LLM_QUEUE)
"""Consumption order of `worker-llm`: priority first."""

_UNACKED = "unacked"
"""Kombu's Redis hash of delivered, not yet acknowledged messages (the running tasks)."""
_TIMEOUT_S = 1.0


def review_queue(priority: bool) -> str:
    """Queue for a model review: `llm_priority` for analyst-initiated material."""
    return LLM_PRIORITY_QUEUE if priority else LLM_QUEUE


ReviewQueueState = Literal["queued", "running", "unknown"]


class ReviewQueuePosition(BaseModel):
    """Where one finding's model review is: waiting (with how many before it) or running."""

    state: ReviewQueueState
    queue: str | None = None
    ahead: int = 0
    """Reviews the worker takes before this one (running ones included)."""
    waiting: int = 0
    """All reviews waiting in both queues."""


def _has(raw: bytes | str, finding_id: str) -> bool:
    return finding_id in (raw.decode(errors="replace") if isinstance(raw, bytes) else raw)


def _finding_index(messages: list[bytes | str], finding_id: str) -> int | None:
    # Messages are LPUSHed and BRPOPed: the last element is taken first.
    for index, raw in enumerate(messages):
        if _has(raw, finding_id):
            return index
    return None


def _running(client: redis.Redis, finding_id: str) -> tuple[int, bool]:
    """Reviews in flight on the `llm` queues, and whether `finding_id` is one of them."""
    count, ours = 0, False
    for raw in client.hvals(_UNACKED):
        try:
            message, _, routing_key = json.loads(raw)
            eta = message.get("headers", {}).get("eta")
        except (ValueError, TypeError, AttributeError):
            continue
        # A retry waiting for its countdown (`eta`) is held by the worker but not running.
        if routing_key in LLM_QUEUES and not eta:
            count += 1
            ours = ours or _has(raw, finding_id)
    return count, ours


def queue_position(finding_id: str, client: redis.Redis | None = None) -> ReviewQueuePosition:
    """Locate the review of `finding_id` in the broker; `unknown` when Redis cannot tell."""
    try:
        client = client or redis.Redis.from_url(get_settings().redis_url, socket_timeout=_TIMEOUT_S)
        lists: dict[str, list[bytes | str]] = {
            name: list(client.lrange(name, 0, -1)) for name in LLM_QUEUES
        }
        running, ours = _running(client, finding_id)
    except redis.RedisError as exc:
        log.warning("review queue unavailable: %s", exc)
        return ReviewQueuePosition(state="unknown")
    waiting = sum(len(messages) for messages in lists.values())
    if ours:
        return ReviewQueuePosition(state="running", ahead=0, waiting=waiting)
    ahead = running
    for name in LLM_QUEUES:
        messages = lists[name]
        index = _finding_index(messages, finding_id)
        if index is not None:
            ahead += len(messages) - 1 - index
            return ReviewQueuePosition(state="queued", queue=name, ahead=ahead, waiting=waiting)
        ahead += len(messages)
    return ReviewQueuePosition(state="unknown", waiting=waiting)
