from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from investwatch_ai.schemas import FirmMatch, Post, RegisteredFirm

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "data" / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def posts() -> dict[str, Post]:
    """Fixture posts keyed by the last two digits of their id ("01".."10")."""
    items = TypeAdapter(list[Post]).validate_python(_load("posts.json"))
    return {str(p.id)[-2:]: p for p in items}


@pytest.fixture(scope="session")
def firms() -> dict[str, RegisteredFirm]:
    """Fixture firms keyed by name."""
    items = TypeAdapter(list[RegisteredFirm]).validate_python(_load("firms.json"))
    return {f.name: f for f in items}


def match(firm: RegisteredFirm, on: str = "author", confidence: float = 1.0) -> FirmMatch:
    return FirmMatch.model_validate(
        {
            "firm": firm.model_dump(),
            "confidence": confidence,
            "method": "domain" if on == "author" else "alias",
            "matched_text": firm.name,
            "on": on,
        }
    )
