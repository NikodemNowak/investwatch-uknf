"""System status for the Monitoring page."""

from __future__ import annotations

from fastapi import APIRouter

from investwatch.status.probe import system_status
from investwatch.status.schemas import SystemStatus

router = APIRouter(tags=["system"])


@router.get("/system")
def get_system() -> SystemStatus:
    """Health of every service, workers per queue and the next scheduled run (cached)."""
    return system_status()
