"""Serve stored artefacts (screenshots, raw HTML) through the API.

Only ports 8000/8080 are published, so the browser cannot reach MinIO's presigned URLs.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Response

from investwatch.storage.minio import get_store

router = APIRouter(prefix="/objects", tags=["objects"])

_ALLOWED = re.compile(r"^(raw|shots|render|media|reports)/[A-Za-z0-9._/-]+$")
_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".pdf": "application/pdf",
}


@router.get("/{key:path}")
def get_object(key: str) -> Response:
    """Return one stored object."""
    if not _ALLOWED.match(key) or ".." in key:
        raise HTTPException(status_code=404, detail="object not found")
    data = get_store().get_bytes(key)
    if data is None:
        raise HTTPException(status_code=404, detail="object not found")
    suffix = key[key.rfind(".") :]
    # Raw pages are evidence, not something to render in our origin.
    media_type = _TYPES.get(suffix, "text/plain; charset=utf-8")
    return Response(
        content=data, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"}
    )
