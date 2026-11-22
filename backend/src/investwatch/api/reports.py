"""Module reports as CSV (Excel-friendly) or JSON, with the findings-list filters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from investwatch.api.deps import SessionDep
from investwatch.api.findings import FiltersDep
from investwatch.core.schemas import ModuleId
from investwatch.db import repo
from investwatch.db.schemas import FindingFilters
from investwatch.reports.export import Separator, to_csv, to_rows
from investwatch.reports.pdf import PdfRenderer, get_pdf_renderer, module_html
from investwatch.reports.schemas import Report, ReportRow

router = APIRouter(prefix="/reports", tags=["reports"])

_SHORT: dict[str, ModuleId] = {
    "m1": "m1_third_party_ad",
    "m2": "m2_risk_disclosure",
    "m3": "m3_shadow_advisory",
}
MAX_ROWS = 10_000
LimitParam = Annotated[int, Query(ge=1, le=MAX_ROWS)]


def _resolve(module: str) -> ModuleId:
    if module in _SHORT:
        return _SHORT[module]
    if module in _SHORT.values():
        return module  # type: ignore[return-value]
    raise HTTPException(status_code=404, detail="unknown module (use m1, m2 or m3)")


def _rows(
    session: Session, module: ModuleId, filters: FindingFilters, limit: int
) -> tuple[list[ReportRow], bool]:
    found = repo.all_findings(session, filters.model_copy(update={"module": module}), limit + 1)
    return [row for f in found[:limit] for row in to_rows(f)], len(found) > limit


LOCAL_TZ = ZoneInfo("Europe/Warsaw")
"""File names carry the analyst's wall-clock time, not UTC (a 21:30 export is not "2030")."""


def _filename(module: ModuleId | str, ext: str) -> str:
    return f"investwatch-{module}-{datetime.now(LOCAL_TZ):%Y%m%d-%H%M}.{ext}"


@router.get("/{module}.csv", response_class=Response)
def report_csv(
    module: str,
    session: SessionDep,
    filters: FiltersDep,
    sep: Annotated[Separator, Query(description="`;` for Excel in the Polish locale")] = ",",
    limit: LimitParam = MAX_ROWS,
) -> Response:
    """Module report as UTF-8 CSV with BOM (opens correctly in Excel)."""
    module_id = _resolve(module)
    rows, truncated = _rows(session, module_id, filters, limit)
    return Response(
        content=to_csv(module_id, rows, sep).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(module_id, "csv")}"',
            "X-Report-Truncated": str(truncated).lower(),
        },
    )


@router.get("/{module}.json")
def report_json(
    module: str,
    session: SessionDep,
    filters: FiltersDep,
    response: Response,
    limit: LimitParam = MAX_ROWS,
) -> Report:
    """Module report as JSON (same rows and filters as the CSV)."""
    module_id = _resolve(module)
    rows, truncated = _rows(session, module_id, filters, limit)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{_filename(module_id, "json")}"'
    )
    return Report.model_validate(
        {
            "module": module_id,
            "generated_at": datetime.now(UTC),
            "count": len(rows),
            "truncated": truncated,
            "items": [r.model_dump() for r in rows],
        }
    )


_TITLES: dict[str, str] = {
    "m1_third_party_ad": "raport M1: reklamy osób trzecich",
    "m2_risk_disclosure": "raport M2: informacja o ryzyku",
    "m3_shadow_advisory": "raport M3: doradztwo bez zezwolenia",
}
PDF_MAX_ROWS = 500
"""A printable table; larger exports belong in the CSV."""


def _describe(filters: FindingFilters) -> str:
    labels = {
        "platform": "platforma",
        "collector": "kolektor",
        "risk_level": "ryzyko",
        "status": "status",
        "date_from": "od",
        "date_to": "do",
        "min_score": "min. wynik",
        "q": "szukaj",
    }
    data = {
        k: ", ".join(map(str, v)) if isinstance(v, list) else v
        for k, v in filters.model_dump(include=set(labels), exclude_none=True).items()
        if v not in ([], "")
    }
    return "Filtry: " + "; ".join(f"{labels[k]} = {v}" for k, v in data.items()) if data else ""


@router.get("/{module}.pdf", response_class=Response)
def report_pdf(
    module: str,
    session: SessionDep,
    filters: FiltersDep,
    renderer: Annotated[PdfRenderer, Depends(get_pdf_renderer)],
    limit: Annotated[int, Query(ge=1, le=PDF_MAX_ROWS)] = PDF_MAX_ROWS,
) -> Response:
    """Module report as an A4 landscape PDF (same rows as the CSV); `all` = the three modules."""
    modules: list[ModuleId] = list(_SHORT.values()) if module == "all" else [_resolve(module)]
    sections = []
    truncated = False
    for module_id in modules:
        rows, cut = _rows(session, module_id, filters, limit)
        sections.append((module_id, rows))
        truncated = truncated or cut
    title = _TITLES[modules[0]] if len(modules) == 1 else "raport zbiorczy M1–M3"
    doc = module_html(
        title, sections, datetime.now(UTC), filters=_describe(filters), truncated=truncated
    )
    stem = modules[0] if len(modules) == 1 else "all"
    name = _filename(stem, "pdf")
    return Response(
        content=renderer.pdf(doc, landscape=True),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Report-Truncated": str(truncated).lower(),
        },
    )
