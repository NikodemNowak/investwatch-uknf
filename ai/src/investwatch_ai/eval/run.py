"""Run golden-set items through the production `analyze()` and collect predictions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

from ..analyze import EMBED_MAX_CHARS, AnalyzeRequest, analyze
from ..classifier.model import module_thresholds
from ..config import AiMode, Settings
from ..llm import OllamaClient
from ..preprocess import clean_text
from ..schemas import Finding, ModuleId, Post, RenderSnapshot, RuleStatus
from .golden import GoldenItem

EVAL_NS = uuid.UUID("0e9a4c7b-8f6d-4b8e-9a3c-5d1f2e7b6a90")
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class Prediction(BaseModel):
    """What the pipeline said about one golden item, for its module."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    module: ModuleId
    score: float
    """Score of the item's module finding; 0 when the router produced none."""
    threshold: float
    predicted: bool
    has_finding: bool
    rules: dict[str, RuleStatus]
    """Rule verdicts of the item's module finding (empty without one)."""
    used_llm: bool
    ms: float
    """`analyze()` wall time for the whole item."""


def load_golden(path: Path) -> list[GoldenItem]:
    """Read `golden.jsonl`."""
    return [
        GoldenItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@cache
def _raw(root: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = Path(root) / "raw" / "posts.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out.setdefault(f"{row['platform']}:{row['external_id']}", row)
    return out


def item_text(root: Path, item: GoldenItem) -> str:
    """Inline text, or the raw post the item references."""
    if item.post.text or not item.text_ref:
        return item.post.text
    row = _raw(str(root)).get(item.text_ref.partition("#")[2])
    return str(row.get("text") or "") if row else ""


def embed_text(root: Path, item: GoldenItem) -> str:
    """The exact text `analyze()` embeds for this item (embedding cache key)."""
    return clean_text(item_text(root, item))[:EMBED_MAX_CHARS]


def _domain(url: str) -> str:
    host = urlsplit(url if "//" in url else f"//{url}").hostname or ""
    return host.lower().removeprefix("www.")


def warning_matches(items: list[GoldenItem], path: Path) -> dict[str, str]:
    """Item id -> KNF warning-list entity, by the domain of the item URL (eval helper)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    by_domain = {
        _domain(d): e["name"] for e in data.get("entities", []) for d in e.get("domains", [])
    }
    out = {}
    for item in items:
        name = by_domain.get(_domain(item.post.url)) or by_domain.get(_domain(item.post.author))
        if name:
            out[item.id] = name
    return out


def to_request(
    root: Path,
    item: GoldenItem,
    embedding: list[float] | None = None,
    knf_warning: str | None = None,
) -> AnalyzeRequest:
    """Build the `/analyze` body the backend would send for this item."""
    text = item_text(root, item)
    post = Post(
        id=uuid.uuid5(EVAL_NS, item.id),
        platform=item.post.platform,
        collector=item.post.collector,
        external_id=item.post.external_id,
        url=item.post.url,
        canonical_url=item.post.url,
        author=item.post.author,
        author_url=item.post.author_url,
        text=text,
        lang=item.post.lang,
        content_hash="",
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=None,
        first_seen_at=EPOCH,
        last_seen_at=EPOCH,
    )
    render = None
    if item.render_path and (root / item.render_path).exists():
        render = RenderSnapshot.model_validate_json(
            (root / item.render_path).read_text(encoding="utf-8")
        )
    return AnalyzeRequest(
        post=post,
        render=render,
        firm_matches=item.firm_matches,
        register_status=item.register_status,
        embedding=embedding,
        knf_warning=knf_warning,
    )


def _module_finding(findings: list[Finding], module: ModuleId) -> Finding | None:
    return next((f for f in findings if f.module == module), None)


def predict(
    root: Path,
    item: GoldenItem,
    settings: Settings,
    mode: AiMode = "rules",
    client: OllamaClient | None = None,
    embedding: list[float] | None = None,
    knf_warning: str | None = None,
) -> Prediction:
    """Analyse one item and read off its module's score and rule verdicts."""
    response = analyze(
        to_request(root, item, embedding, knf_warning), settings, client=client, mode=mode
    )
    finding = _module_finding(response.findings, item.module)
    threshold = module_thresholds(settings)[item.module]
    score = finding.score if finding else 0.0
    return Prediction(
        item_id=item.id,
        module=item.module,
        score=score,
        threshold=threshold,
        predicted=score >= threshold,
        has_finding=finding is not None,
        rules={r.rule_id: r.status for r in finding.rules} if finding else {},
        used_llm=finding.used_llm if finding else False,
        ms=response.timings_ms.get("total", 0.0),
    )


def run(
    root: Path,
    items: list[GoldenItem],
    settings: Settings,
    mode: AiMode = "rules",
    client: OllamaClient | None = None,
    embeddings: dict[str, list[float]] | None = None,
    warnings: dict[str, str] | None = None,
) -> list[Prediction]:
    """Predict every item that has text (excluded items and items without text are skipped).

    Real items whose text was withdrawn from `raw/posts.jsonl` (or never stored, e.g. YouTube
    descriptions waiting for an official API fetch) cannot be scored and are left out.
    """
    embeddings = embeddings or {}
    warnings = warnings or {}
    return [
        predict(root, i, settings, mode, client, embeddings.get(i.id), warnings.get(i.id))
        for i in items
        if not i.excluded and item_text(root, i).strip()
    ]
