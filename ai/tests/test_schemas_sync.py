from __future__ import annotations

from pathlib import Path

import pytest

AI_SCHEMAS = Path(__file__).resolve().parents[1] / "src" / "investwatch_ai" / "schemas.py"
BACKEND_SCHEMAS = (
    Path(__file__).resolve().parents[2] / "backend" / "src" / "investwatch" / "core" / "schemas.py"
)


@pytest.mark.skipif(not BACKEND_SCHEMAS.exists(), reason="backend/ not present (e.g. Docker build)")
def test_contract_copy_is_identical_to_backend() -> None:
    assert AI_SCHEMAS.read_bytes() == BACKEND_SCHEMAS.read_bytes(), (
        "ai/src/investwatch_ai/schemas.py must be a verbatim copy of "
        "backend/src/investwatch/core/schemas.py; run: "
        "cp backend/src/investwatch/core/schemas.py ai/src/investwatch_ai/schemas.py"
    )
