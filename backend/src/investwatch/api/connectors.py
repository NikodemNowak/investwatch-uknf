"""Data connectors and their status (the Sources / Monitoring page badges)."""

from __future__ import annotations

from fastapi import APIRouter

from investwatch.collectors.policy import ConnectorInfo, connector_infos
from investwatch.config import get_settings

router = APIRouter(prefix="/connectors", tags=["sources"])


@router.get("")
def list_connectors() -> list[ConnectorInfo]:
    """Every connector: access mode, status ("wymaga klucza"...), legal basis, how to get access."""
    return connector_infos(get_settings())
