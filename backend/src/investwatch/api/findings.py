"""Findings list, detail and analyst status."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from investwatch.api.deps import SessionDep
from investwatch.api.schemas import FindingPatch
from investwatch.core.schemas import ModuleId, Platform, RiskLevel, Status
from investwatch.db import repo
from investwatch.db.schemas import FindingFilters, FindingsPage, FindingView
from investwatch.jobs.queues import ReviewQueuePosition, queue_position

router = APIRouter(prefix="/findings", tags=["findings"])


def _as_datetime(value: datetime | date | None, *, end_of_day: bool) -> datetime | None:
    """Dates are whole UTC days, so `to=2026-11-21` includes that day."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.combine(value, time.max if end_of_day else time.min, tzinfo=UTC)


def finding_filters(
    platform: Annotated[
        list[Platform] | None, Query(description="Repeat for any of several platforms")
    ] = None,
    collector: Annotated[str | None, Query(description="Source collector, e.g. `web`")] = None,
    risk_level: Annotated[
        list[RiskLevel] | None, Query(description="Repeat for any of several levels")
    ] = None,
    status: Annotated[
        list[Status] | None,
        Query(description="Repeat for any of several, e.g. `status=new&status=in_review`"),
    ] = None,
    date_from: Annotated[
        date | datetime | None, Query(alias="from", description="ISO date or datetime")
    ] = None,
    date_to: Annotated[
        date | datetime | None,
        Query(alias="to", description="ISO date (inclusive, whole day) or datetime"),
    ] = None,
    min_score: Annotated[float | None, Query(ge=0, le=1)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal["created_at", "score"] = "created_at",
) -> FindingFilters:
    """Query filters shared by the findings list and the module reports."""
    return FindingFilters(
        platform=platform or [],
        collector=collector,
        risk_level=risk_level or [],
        status=status or [],
        date_from=_as_datetime(date_from, end_of_day=False),
        date_to=_as_datetime(date_to, end_of_day=True),
        min_score=min_score,
        q=q,
        sort=sort,
    )


FiltersDep = Annotated[FindingFilters, Depends(finding_filters)]


@router.get("")
def list_findings(
    session: SessionDep,
    filters: FiltersDep,
    module: ModuleId | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> FindingsPage:
    """List findings, newest (or highest score) first."""
    update = {"module": module, "page": page, "page_size": page_size}
    return repo.list_findings(session, filters.model_copy(update=update))


@router.get("/{finding_id}")
def get_finding(finding_id: uuid.UUID, session: SessionDep) -> FindingView:
    """Return one finding with its post."""
    finding = repo.get_finding(session, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding


@router.get("/{finding_id}/review-queue")
def get_review_queue(finding_id: uuid.UUID, session: SessionDep) -> ReviewQueuePosition:
    """Where the finding's model review waits: queue, reviews before it, or running now."""
    finding = repo.get_finding(session, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    if finding.llm_review != "queued":
        return ReviewQueuePosition(state="unknown")
    return queue_position(str(finding_id))


@router.patch("/{finding_id}")
def patch_finding(finding_id: uuid.UUID, body: FindingPatch, session: SessionDep) -> FindingView:
    """Set the analyst status (`new`, `in_review`, `confirmed`, `dismissed`)."""
    finding = repo.update_finding_status(session, finding_id, body.status)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding
