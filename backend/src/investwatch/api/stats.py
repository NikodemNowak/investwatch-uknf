"""Dashboard statistics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from investwatch.api.deps import SessionDep
from investwatch.core.schemas import ModuleId, TrendBucket, TrendSeries
from investwatch.db import repo
from investwatch.db.schemas import Summary

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/trend")
def get_trend(
    session: SessionDep,
    bucket: TrendBucket | Literal["auto"] = "day",
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    module: ModuleId | None = None,
) -> TrendSeries:
    """Findings per hour/day/week and module, split by risk level (default: last 14 days).

    `bucket=auto` (what the dashboard asks for) picks hourly buckets when every finding of the
    last 14 days is from the last 48 hours, daily otherwise; `from` / `to` are then ignored.
    """
    if bucket == "auto":
        return repo.trend_auto(session, datetime.now(UTC), module)
    if bucket == "hour":
        raise HTTPException(status_code=422, detail="hourly buckets only with bucket=auto")
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=13)
    if start > end or (end - start).days > 366:
        raise HTTPException(status_code=422, detail="invalid date range")
    return repo.trend(session, bucket, start, end, module)


@router.get("/summary")
def get_summary(session: SessionDep) -> Summary:
    """Headline counts."""
    return repo.summary(session)
