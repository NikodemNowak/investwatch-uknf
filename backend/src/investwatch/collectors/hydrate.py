"""Restore YouTube rows of a JSONL file (ids + labels) through the official API.

Usage: `python -m investwatch.collectors.hydrate data/golden/raw/posts.jsonl --out /tmp/x.jsonl`

Needs `YOUTUBE_API_KEY`; costs one quota unit per 50 videos. Videos that no longer exist stay
without text and are flagged `removed`. Write the result outside the repository: the API policy
allows keeping the data for at most 30 days.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from investwatch.collectors.official.youtube_api import YouTubeApiCollector
from investwatch.config import get_settings

log = logging.getLogger(__name__)


def hydrate(rows: list[dict[str, Any]], collector: YouTubeApiCollector) -> list[dict[str, Any]]:
    """Rows with YouTube text, author and dates filled in from `videos.list`."""
    ids = [str(r["external_id"]) for r in rows if r.get("platform") == "youtube"]
    if not ids:
        return rows
    items, missing = collector.refresh(ids)
    by_id = {i.external_id: i for i in items}
    out = []
    for row in rows:
        item = by_id.get(str(row.get("external_id"))) if row.get("platform") == "youtube" else None
        if item is not None:
            row = {
                **row,
                "text": item.text,
                "author": item.author,
                "author_url": item.author_url,
                "lang": item.lang,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "fetched_at": (item.raw or {}).get("fetched_at"),
                "candidate_domains": (item.raw or {}).get("candidate_domains") or [],
            }
            row.pop("content", None)
        elif row.get("platform") == "youtube" and str(row.get("external_id")) in missing:
            row = {**row, "removed": True}
        out.append(row)
    return out


def main() -> None:
    """Read the JSONL, hydrate YouTube rows, write the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not get_settings().youtube_api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set")
    rows = [json.loads(line) for line in args.src.read_text(encoding="utf-8").splitlines() if line]
    result = hydrate(rows, YouTubeApiCollector())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in result), encoding="utf-8"
    )
    log.info("wrote %d rows to %s", len(result), args.out)


if __name__ == "__main__":
    main()
