"""Result aggregator: entities (firms, advertisers) with their M1/M2/M3 findings merged."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from investwatch.api.deps import SessionDep
from investwatch.api.findings import FiltersDep
from investwatch.core.schemas import ModuleId
from investwatch.db import repo
from investwatch.db.schemas import FindingFilters, FindingView
from investwatch.entities.aggregate import aggregate, entity_detail, matches_name
from investwatch.entities.schemas import EntitiesPage, EntityDetail

router = APIRouter(prefix="/entities", tags=["entities"])

MAX_FINDINGS = 5000
"""Findings read per aggregation; enough for the monitored volume, flagged when exceeded."""


def _findings(session: Session, filters: FindingFilters) -> tuple[list[FindingView], bool]:
    found = repo.all_findings(session, filters, MAX_FINDINGS + 1)
    return found[:MAX_FINDINGS], len(found) > MAX_FINDINGS


def _sources(session: Session, findings: list[FindingView]) -> dict[UUID, str]:
    return repo.firm_sources(session, {f.firm.id for f in findings if f.firm is not None})


@router.get("")
def list_entities(
    session: SessionDep,
    filters: FiltersDep,
    module: ModuleId | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> EntitiesPage:
    """Entities over the filtered findings, most serious first.

    The findings filters (`from`, `to`, `platform`, `status`, `risk_level`, `module`) choose which
    findings are merged; `q` searches entity names, aliases and domains instead of the text.
    """
    query = filters.q
    findings, truncated = _findings(
        session, filters.model_copy(update={"module": module, "q": None})
    )
    entities = aggregate(findings, _sources(session, findings))
    if query:
        entities = [e for e in entities if matches_name(e, query)]
    return EntitiesPage(
        items=entities[:limit], total=len(entities), findings=len(findings), truncated=truncated
    )


@router.get("/{key:path}")
def get_entity(key: str, session: SessionDep) -> EntityDetail:
    """One entity with every finding that belongs to it (all modules, statuses and dates)."""
    findings, _ = _findings(session, FindingFilters())
    detail = entity_detail(findings, _sources(session, findings), key)
    if detail is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return detail
