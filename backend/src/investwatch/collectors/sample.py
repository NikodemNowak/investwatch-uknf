"""Loads contract fixtures (`data/fixtures/*.json`) and sample folders as collected items.

Sample folders (`data/samples/`: the UKNF booth samples; `data/fixtures/synthetic/`: synthetic
records in the shape of the official APIs) are read with the file importer, so every item
carries `access_mode=file_import`, the file's SHA-256 and, for synthetic data, `synthetic`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from investwatch.collectors.imports.file_import import ImportFileError, import_file
from investwatch.collectors.schemas import CollectedItem
from investwatch.config import get_settings
from investwatch.core.schemas import Finding, Post, RegisteredFirm, RenderSnapshot

log = logging.getLogger(__name__)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_posts(directory: Path | None = None) -> list[Post]:
    """Return `posts.json`."""
    base = directory or get_settings().fixtures_dir
    return TypeAdapter(list[Post]).validate_python(_read(base / "posts.json"))


def load_findings(directory: Path | None = None) -> list[Finding]:
    """Return `findings.json`."""
    base = directory or get_settings().fixtures_dir
    return TypeAdapter(list[Finding]).validate_python(_read(base / "findings.json"))


def load_firms(directory: Path | None = None) -> list[RegisteredFirm]:
    """Return `firms.json`."""
    base = directory or get_settings().fixtures_dir
    return TypeAdapter(list[RegisteredFirm]).validate_python(_read(base / "firms.json"))


def load_render_snapshot(directory: Path | None = None) -> RenderSnapshot:
    """Return `render_snapshot.json`."""
    base = directory or get_settings().fixtures_dir
    return RenderSnapshot.model_validate(_read(base / "render_snapshot.json"))


def _format_for(path: Path) -> str:
    name = path.name.lower()
    if "meta" in name:
        return "meta_ads_csv" if path.suffix == ".csv" else "meta_ads_json"
    if "tiktok" in name:
        return "tiktok_ccl_json"
    if "youtube" in name:
        return "youtube_api_json"
    return "uknf_sample"


def load_folder(directory: Path) -> list[CollectedItem]:
    """Every JSON / JSONL / CSV file of a sample folder, imported as files."""
    items: list[CollectedItem] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".json", ".jsonl", ".csv"} or not path.is_file():
            continue
        try:
            items += import_file(
                _format_for(path),
                path.read_bytes(),
                filename=path.name,
                imported_by="sample",
                provenance_note=f"sample folder {directory.name}",
            )
        except ImportFileError as exc:
            log.warning("sample %s skipped: %s", path, exc)
    return items


class SampleCollector:
    """Replays `posts.json` or a sample folder as if freshly collected."""

    name = "sample"

    def collect(self, target: str) -> list[CollectedItem]:
        """`target`: empty (default fixtures), `samples`, `synthetic`, or a directory."""
        settings = get_settings()
        named = {
            "samples": settings.data_dir / "samples",
            "synthetic": settings.fixtures_dir / "synthetic",
        }
        directory = named.get(target.strip()) or (Path(target) if target else None)
        if directory is not None and not (directory / "posts.json").is_file():
            return load_folder(directory) if directory.is_dir() else []
        posts = load_posts(directory)
        return [
            CollectedItem(
                platform=p.platform,
                collector=p.collector,
                external_id=p.external_id,
                url=p.url,
                author=p.author,
                author_url=p.author_url,
                text=p.text,
                lang=p.lang,
                published_at=p.published_at,
                fetch_status=p.fetch_status,
                post_id=p.id,
            )
            for p in posts
        ]
