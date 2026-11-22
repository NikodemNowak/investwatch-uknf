"""Posts and their stored artefacts (render snapshot, screenshots)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response

from investwatch.api.deps import SessionDep
from investwatch.core.schemas import Post, RenderSnapshot, Viewport
from investwatch.db import repo
from investwatch.storage.minio import get_store

router = APIRouter(prefix="/posts", tags=["posts"])


def _post(session: SessionDep, post_id: uuid.UUID) -> Post:
    post = repo.get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="post not found")
    return post


@router.get("/{post_id}")
def get_post(post_id: uuid.UUID, session: SessionDep) -> Post:
    """Return one post."""
    return _post(session, post_id)


@router.get("/{post_id}/render")
def get_render(post_id: uuid.UUID, session: SessionDep) -> RenderSnapshot:
    """Return the layout snapshot (404 when the page was not rendered)."""
    post = _post(session, post_id)
    data = get_store().get_bytes(post.render_key) if post.render_key else None
    if data is None:
        raise HTTPException(status_code=404, detail="no render snapshot")
    return RenderSnapshot.model_validate_json(data)


@router.get("/{post_id}/screenshots/{viewport}", response_class=Response)
def get_screenshot(post_id: uuid.UUID, viewport: Viewport, session: SessionDep) -> Response:
    """Return a PNG screenshot of the post in one viewport (404 when missing)."""
    key = _post(session, post_id).screenshot_keys.get(viewport)
    data = get_store().get_bytes(key) if key else None
    if data is None:
        raise HTTPException(status_code=404, detail="no screenshot")
    return Response(content=data, media_type="image/png")
