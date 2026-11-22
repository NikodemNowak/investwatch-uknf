"""Curated starting sources for the live collectors (`data/seeds/sources.yaml`)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, TypeAdapter

from investwatch.config import get_settings
from investwatch.core.schemas import ModuleId

log = logging.getLogger(__name__)


class SeedSource(BaseModel):
    """One row for the `sources` table."""

    name: str
    collector: str
    target: str
    module_hint: ModuleId | None = None
    cron: str
    enabled: bool = False


def seeds_path() -> Path:
    """Default location of the seed list."""
    return get_settings().data_dir / "seeds" / "sources.yaml"


def load_seed_sources(path: Path | None = None) -> list[SeedSource]:
    """Read the seed list; a missing file means no live sources."""
    path = path or seeds_path()
    if not path.is_file():
        log.warning("no seed sources at %s", path)
        return []
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TypeAdapter(list[SeedSource]).validate_python(data.get("sources", []))
