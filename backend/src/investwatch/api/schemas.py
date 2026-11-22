"""HTTP request/response bodies that are not part of the shared contract."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from investwatch.core.schemas import ModuleId, Status


class FindingPatch(BaseModel):
    """Body of `PATCH /api/findings/{id}`."""

    status: Status


class CheckRequest(BaseModel):
    """Body of `POST /api/check`: a URL or pasted text (exactly one)."""

    url: str | None = Field(default=None, max_length=2048)
    text: str | None = Field(default=None, max_length=50_000)

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if bool(self.url) == bool(self.text and self.text.strip()):
            raise ValueError("provide exactly one of `url` or `text`")
        return self


JobState = Literal["queued", "running", "done", "failed"]


class CheckJob(BaseModel):
    """A queued "check URL" job; progress also arrives as Socket.IO `job` events."""

    job_id: str
    state: JobState
    post_id: str | None = None
    finding_ids: list[str] = []
    error: str | None = None


class SourceCreate(BaseModel):
    """Body of `POST /api/sources`."""

    name: str = Field(min_length=1, max_length=200)
    collector: str = Field(min_length=1, max_length=50)
    target: str = Field(min_length=0, max_length=2048)
    module_hint: ModuleId | None = None
    cron: str = "0 */6 * * *"
    enabled: bool = True


class SourcePatch(BaseModel):
    """Body of `PATCH /api/sources/{id}` (only the fields sent are changed)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    target: str | None = Field(default=None, max_length=2048)
    module_hint: ModuleId | None = None
    cron: str | None = None
    enabled: bool | None = None
