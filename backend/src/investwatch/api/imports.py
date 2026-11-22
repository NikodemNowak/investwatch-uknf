"""File imports and analyst submissions: material that reaches us without any fetching."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from investwatch.api.deps import SessionDep
from investwatch.collectors.imports.analyst import submission_item
from investwatch.collectors.imports.file_import import (
    IMPORT_FORMATS,
    MAX_IMPORT_BYTES,
    ImportFileError,
    import_file,
)
from investwatch.collectors.schemas import CollectedItem
from investwatch.core.schemas import ModuleId
from investwatch.jobs.queues import CHECK_QUEUE
from investwatch.jobs.tasks import analyze_post
from investwatch.pipeline.analyze import ingest_item

router = APIRouter(tags=["imports"])

MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024


class ImportResult(BaseModel):
    """What an import or submission stored."""

    sha256: str
    items: int
    created: int
    post_ids: list[str]
    queued_for_analysis: int


async def _read(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"file larger than {limit // 2**20} MB")
    return data


def _store(
    session: SessionDep, items: list[CollectedItem], sha256: str, *, priority: bool = False
) -> ImportResult:
    created, post_ids, queue = 0, [], []
    for item in items:
        result = ingest_item(session, item)
        created += int(result.created)
        post_ids.append(str(result.post.id))
        if result.changed and result.post.fetch_status == "ok":
            queue.append(str(result.post.id))
    session.commit()
    for post_id in queue:
        if priority:  # an analyst waits for this one: skip the batch `analyze` backlog
            analyze_post.apply_async((post_id,), {"priority": True}, queue=CHECK_QUEUE)
        else:
            analyze_post.delay(post_id)
    return ImportResult(
        sha256=sha256,
        items=len(items),
        created=created,
        post_ids=post_ids,
        queued_for_analysis=len(queue),
    )


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def post_import(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()],
    module_hint: Annotated[ModuleId | None, Form()] = None,
    provenance_note: Annotated[str, Form(max_length=2000)] = "",
    imported_by: Annotated[str, Form(max_length=200)] = "analyst",
) -> ImportResult:
    """Import a Meta Ad Library export, a TikTok CCL export or UKNF samples (CSV/JSON/JSONL)."""
    if format not in IMPORT_FORMATS:
        raise HTTPException(
            status_code=422, detail=f"format must be one of: {', '.join(IMPORT_FORMATS)}"
        )
    content = await _read(file, MAX_IMPORT_BYTES)
    try:
        items = import_file(
            format,
            content,
            filename=file.filename or "",
            imported_by=imported_by,
            provenance_note=provenance_note,
            module_hint=module_hint,
        )
    except ImportFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _store(session, items, hashlib.sha256(content).hexdigest())


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def post_submission(
    session: SessionDep,
    text: Annotated[str, Form(min_length=1, max_length=50_000)],
    url: Annotated[str, Form(max_length=2048)] = "",
    note: Annotated[str, Form(max_length=2000)] = "",
    submitted_by: Annotated[str, Form(max_length=200)] = "analyst",
    screenshot: Annotated[UploadFile | None, File()] = None,
) -> ImportResult:
    """Record what an analyst saw: URL + pasted text (+ screenshot). Nothing is fetched."""
    if not text.strip():
        raise HTTPException(status_code=422, detail="text is empty")
    shot = await _read(screenshot, MAX_SCREENSHOT_BYTES) if screenshot is not None else None
    if shot is not None and not shot.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="screenshot must be a PNG image")
    item = submission_item(text, url or None, screenshot=shot, submitted_by=submitted_by, note=note)
    digest = hashlib.sha256(f"{url}\n{text}".encode()).hexdigest()
    # One item an analyst is looking at right now: its model review jumps the batch backlog.
    return _store(session, [item], digest, priority=True)
