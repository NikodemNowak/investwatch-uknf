"""Threshold calibration computed from the `labels` table.

Labels come from the golden set (`source=golden`, loaded by `seed` with the scores of the last
`make eval`) and from analyst decisions (`source=analyst`: confirmed = 1, dismissed = 0, with
the finding's current score). Below `min_labels` labels the UI shows an empty state.
"""

from __future__ import annotations

from fastapi import APIRouter

from investwatch.api.deps import SessionDep
from investwatch.calibration import build_report
from investwatch.core.schemas import CalibrationReport, ModuleId
from investwatch.db import repo

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/{module}")
def get_calibration(
    module: ModuleId, session: SessionDep, source: repo.LabelSource = "all"
) -> CalibrationReport:
    """Precision/recall/F1/F2 per threshold and the score histogram for one module."""
    labelled, unlabelled, counts = repo.calibration_inputs(session, module, source)
    threshold = repo.get_thresholds(session).for_module(module)
    return build_report(module, labelled, unlabelled, threshold, counts)
