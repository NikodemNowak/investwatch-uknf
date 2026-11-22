"""Liveness endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Health(BaseModel):
    """Health check response."""

    status: str
    version: str


@router.get("/health")
def health() -> Health:
    """Report that the API is up."""
    return Health(status="ok", version="0.1.0")
