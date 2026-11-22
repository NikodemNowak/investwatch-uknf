"""Provenance ("Pod maską") and the one-page evidence PDF of a finding."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from investwatch.api.deps import SessionDep
from investwatch.db import repo
from investwatch.db.schemas import FindingView
from investwatch.provenance.build import under_the_hood
from investwatch.provenance.schemas import UnderTheHood
from investwatch.reports.pdf import (
    EvidenceCrop,
    PdfRenderer,
    evidence_target,
    finding_html,
    get_pdf_renderer,
)
from investwatch.storage.minio import get_store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/findings", tags=["findings"])
PdfDep = Annotated[PdfRenderer, Depends(get_pdf_renderer)]


def _finding(session: SessionDep, finding_id: uuid.UUID) -> FindingView:
    finding = repo.get_finding(session, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding


@router.get("/{finding_id}/trace")
def get_trace(finding_id: uuid.UUID, session: SessionDep) -> UnderTheHood:
    """How the material was collected, stored (keys, SHA-256) and analysed, step by step."""
    return under_the_hood(session, _finding(session, finding_id))


def _crop(finding: FindingView, renderer: PdfRenderer) -> EvidenceCrop | None:
    target = evidence_target(finding)
    if target is None:
        return None
    rule, viewport, bbox = target
    try:
        png = get_store().get_bytes(finding.post.screenshot_keys[viewport])
        return EvidenceCrop(rule, viewport, renderer.crop(png, bbox, viewport)) if png else None
    except Exception:  # the report still goes out, without the picture
        log.exception("cannot crop the evidence of %s", finding.id)
        return None


@router.get("/{finding_id}/report.pdf", response_class=Response)
def finding_pdf(finding_id: uuid.UUID, session: SessionDep, renderer: PdfDep) -> Response:
    """One-page evidence report (A4 PDF) to attach to a letter."""
    finding = _finding(session, finding_id)
    hood = under_the_hood(session, finding)
    doc = finding_html(finding, hood, _crop(finding, renderer), datetime.now(UTC))
    name = f"investwatch-raport-{str(finding.id)[:8]}-{datetime.now(UTC):%Y%m%d}.pdf"
    return Response(
        content=renderer.pdf(doc, one_page=True),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
