"""Socket.IO event payloads besides the contract `Alert`."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

JobStage = Literal["queued", "fetched", "analyzed", "failed"]


class JobEvent(BaseModel):
    """Progress of a "check URL" job (Socket.IO event `job`, `JobEvent` in api/types.ts)."""

    job_id: str
    stage: JobStage
    finding_ids: list[UUID] = []
    error: str | None = None
    post_id: UUID | None = None
    duplicate_of: UUID | None = None
    """Set when the post repeats an earlier one: no new findings, no alert."""
