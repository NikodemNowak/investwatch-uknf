"""Check URL: queue one URL or pasted text for collection and analysis."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from investwatch.api.schemas import CheckJob, CheckRequest, JobState
from investwatch.collectors.base import url_rejection
from investwatch.collectors.official.youtube_api import video_id
from investwatch.collectors.policy import collector_ready, platform_rejection
from investwatch.config import get_settings
from investwatch.jobs.tasks import check_url
from investwatch.realtime.emitter import emit_job, load_job
from investwatch.realtime.schemas import JobEvent, JobStage

router = APIRouter(prefix="/check", tags=["check"])

PLATFORM_REFUSAL = (
    "Tej strony nie pobieramy automatycznie: serwisy społecznościowe (Facebook, Instagram, "
    "TikTok) na to nie pozwalają. Zgłoś materiał ręcznie: wklej treść posta lub reklamy "
    "i dołącz zrzut ekranu, jeśli go masz."
)

_STATE: dict[JobStage, JobState] = {
    "queued": "queued",
    "fetched": "running",
    "analyzed": "done",
    "failed": "failed",
}


def _job(event: JobEvent) -> CheckJob:
    return CheckJob(
        job_id=event.job_id,
        state=_STATE[event.stage],
        post_id=str(event.post_id) if event.post_id else None,
        finding_ids=[str(f) for f in event.finding_ids],
        error=event.error,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def post_check(body: CheckRequest) -> CheckJob:
    """Queue a check; follow it with `GET /api/check/{job_id}` or Socket.IO `job` events."""
    url = body.url.strip() if body.url else None
    if url and platform_rejection(url):
        if not video_id(url):
            raise HTTPException(
                status_code=422,
                # `code` lets the dashboard offer the "Zgłoś materiał" form for this URL.
                detail={"code": "platform_url", "message": PLATFORM_REFUSAL, "url": url},
            )
        if collector_ready("youtube", get_settings()) is not None:
            raise HTTPException(status_code=409, detail="YouTube: wymaga klucza (YOUTUBE_API_KEY)")
    elif url:
        reason = url_rejection(url, get_settings().allowed_internal_hosts)
        if reason:
            raise HTTPException(status_code=422, detail=reason)
    job_id = uuid.uuid4().hex
    queued = JobEvent(job_id=job_id, stage="queued")
    emit_job(queued)
    check_url.apply_async(kwargs={"job_id": job_id, "url": url, "text": body.text}, task_id=job_id)
    return _job(load_job(job_id) or queued)


@router.get("/{job_id}")
def get_check(job_id: str) -> CheckJob:
    """Return the latest state of a check job."""
    event = load_job(job_id)
    if event is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job(event)
