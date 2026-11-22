"""Monitored sources and their run history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from croniter import croniter
from fastapi import APIRouter, HTTPException, status

from investwatch.api.deps import SessionDep
from investwatch.api.schemas import SourceCreate, SourcePatch
from investwatch.collectors.policy import (
    ConnectorInfo,
    access_mode_of,
    collector_ready,
    connector_infos,
    source_connector,
)
from investwatch.collectors.registry import COLLECTORS
from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.schemas import ScrapeRun, Source
from investwatch.jobs.tasks import next_run, scrape_source

router = APIRouter(prefix="/sources", tags=["sources"])


def _validate_cron(cron: str) -> None:
    if not croniter.is_valid(cron):
        raise HTTPException(status_code=422, detail=f"invalid cron expression: {cron}")


def _with_connector(source: Source) -> Source:
    info = source_connector(source.collector, get_settings())
    return source.model_copy(
        update={
            "access_mode": info.access_mode if info else access_mode_of(source.collector),
            "connector_status": info.status if info else "ready",
            "connector_reason": info.how_to if info and info.status == "disabled" else None,
        }
    )


@router.get("")
def list_sources(session: SessionDep) -> list[Source]:
    """All sources, each with its connector's access mode and status."""
    return [_with_connector(s) for s in repo.list_sources(session)]


@router.get("/connectors")
def list_connectors() -> list[ConnectorInfo]:
    """Every data connector: access mode, status ("wymaga klucza"...), how to get access."""
    return connector_infos(get_settings())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_source(body: SourceCreate, session: SessionDep) -> Source:
    """Add a source; it first runs on the next scheduler tick."""
    if body.collector not in COLLECTORS:
        raise HTTPException(status_code=422, detail=f"unknown collector: {body.collector}")
    _validate_cron(body.cron)
    return _with_connector(repo.create_source(session, **body.model_dump()))


@router.patch("/{source_id}")
def patch_source(source_id: uuid.UUID, body: SourcePatch, session: SessionDep) -> Source:
    """Change selected fields; a new cron reschedules the source."""
    fields = body.model_dump(exclude_unset=True)
    if "cron" in fields and fields["cron"] is not None:
        _validate_cron(fields["cron"])
        fields["next_run_at"] = next_run(fields["cron"], datetime.now(UTC))
    source = repo.update_source(session, source_id, **fields)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return _with_connector(source)


@router.get("/{source_id}/runs")
def list_runs(source_id: uuid.UUID, session: SessionDep) -> list[ScrapeRun]:
    """Latest runs of a source."""
    if repo.get_source(session, source_id) is None:
        raise HTTPException(status_code=404, detail="source not found")
    return repo.list_runs(session, source_id)


@router.post("/{source_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_source(source_id: uuid.UUID, session: SessionDep) -> Source:
    """Queue the source now, outside its schedule."""
    source = repo.get_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    blocked = collector_ready(source.collector, get_settings())
    if blocked is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "connector": blocked.name,
                "status": blocked.status,
                "requires": blocked.requires,
                "how_to": blocked.how_to,
            },
        )
    session.commit()
    scrape_source.delay(str(source_id))
    return _with_connector(source)
