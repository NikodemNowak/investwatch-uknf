"""Runtime settings editable from the dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from investwatch.api.deps import SessionDep
from investwatch.db import repo
from investwatch.db.schemas import Thresholds

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/thresholds")
def get_thresholds(session: SessionDep) -> Thresholds:
    """Alert threshold per module."""
    return repo.get_thresholds(session)


@router.put("/thresholds")
def put_thresholds(body: Thresholds, session: SessionDep) -> Thresholds:
    """Replace the alert thresholds."""
    return repo.set_thresholds(session, body)
