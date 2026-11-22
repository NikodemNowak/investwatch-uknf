"""KNF register firms: search, detail, sync status (the "Rejestr" page)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from investwatch.api.deps import SessionDep
from investwatch.core.schemas import FirmKind
from investwatch.db import repo
from investwatch.jobs.tasks import sync_registry as sync_registry_task
from investwatch.registry.schemas import FirmDetail, FirmsPage, RegistryStatus, SyncQueued

router = APIRouter(prefix="/firms", tags=["registry"])


@router.get("")
def list_firms(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: FirmKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FirmsPage:
    """Active firms, searchable by name, trade/former name or domain (diacritics-insensitive)."""
    total, items = repo.search_firms(session, q, kind, limit, offset)
    return FirmsPage(total=total, items=items)


@router.get("/status")
def registry_status(session: SessionDep) -> RegistryStatus:
    """Last register syncs (live or snapshot) and active firm counts per register."""
    return repo.registry_status(session)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_registry(live: bool | None = None) -> SyncQueued:
    """Queue a register sync now (`live=false` reloads the committed snapshot)."""
    result = sync_registry_task.delay(live)
    return SyncQueued(task_id=str(result.id), live=live)


@router.get("/{firm_id}")
def firm_detail(firm_id: uuid.UUID, session: SessionDep) -> FirmDetail:
    """One firm: register facts, KNF link, domains and number of findings."""
    detail = repo.get_firm_detail(session, firm_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="firm not found")
    return detail
