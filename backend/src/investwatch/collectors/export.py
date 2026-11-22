"""Run the seed sources once and export what came back as JSONL (golden-set candidates).

Usage: `python -m investwatch.collectors.export --limit 10 --out ../data/golden/raw/posts.jsonl`

Only public content and public handles are written: no HTML, no media, no signed URLs.
Items that were blocked or failed are reported on stderr, not exported. Every row records how
it was obtained (`access_mode`). YouTube rows are reduced to ids (`--youtube-ids-only`, default)
because the YouTube API policy forbids keeping API data beyond 30 days; restore their text with
`python -m investwatch.collectors.hydrate`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from investwatch.collectors.registry import get_collector
from investwatch.collectors.schemas import CollectedItem
from investwatch.collectors.seeds import SeedSource, load_seed_sources

log = logging.getLogger(__name__)

_YT_SEARCH = re.compile(r"^(?:ytsearch\d*:|search:(?:\d{1,3}:)?)")
_LIMIT = re.compile(r"^\d{1,3}:")
MAX_TEXT = 20_000


def with_limit(seed: SeedSource, limit: int) -> str:
    """The seed's target asking for `limit` items."""
    target = seed.target
    if seed.collector == "youtube" and _YT_SEARCH.match(target):
        return _YT_SEARCH.sub(f"search:{limit}:", target)
    if seed.collector in {"meta_ad_library", "tiktok", "site"} and not target.startswith("http"):
        return f"{limit}:{_LIMIT.sub('', target)}"
    return target


def record(item: CollectedItem, seed: SeedSource, target: str) -> dict[str, Any]:
    """Public fields of one item plus provenance."""
    raw = item.raw or {}
    return {
        "platform": item.platform,
        "collector": item.collector,
        "external_id": item.external_id,
        "url": item.url,
        "author": item.author,
        "author_url": item.author_url,
        "text": item.text[:MAX_TEXT],
        "lang": item.lang,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": raw.get("fetched_at"),
        "module_hint": seed.module_hint,
        "source_name": seed.name,
        "target": target,
        "candidate_domains": raw.get("candidate_domains") or [],
        "discovered_by": raw.get("discovered_by"),
        "access_mode": raw.get("access_mode"),
        "legal_basis": raw.get("legal_basis"),
    }


def ids_only(row: dict[str, Any]) -> dict[str, Any]:
    """A YouTube row without API content (id, URL, labels and provenance only)."""
    keep = ("platform", "collector", "external_id", "url", "module_hint", "source_name", "target")
    return {
        **{k: row.get(k) for k in keep},
        "text": "",
        "access_mode": "official_api",
        "content": "hydrate with python -m investwatch.collectors.hydrate",
    }


def main() -> None:
    """Collect every seed source once and write the JSONL file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--collector", action="append", help="only these collectors")
    parser.add_argument(
        "--youtube-full", action="store_true", help="keep YouTube text (local use, <= 30 days)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for seed in load_seed_sources():
        if args.collector and seed.collector not in args.collector:
            continue
        target = with_limit(seed, args.limit)
        items = get_collector(seed.collector).collect(target)
        ok = 0
        for item in items:
            key = (item.platform, item.external_id)
            if item.fetch_status != "ok" or key in seen:
                if item.fetch_status != "ok":
                    log.warning("%s: %s %s", seed.name, item.fetch_status, item.error)
                continue
            seen.add(key)
            row = record(item, seed, target)
            rows.append(row if args.youtube_full or item.platform != "youtube" else ids_only(row))
            ok += 1
        log.info("%s: %d items, %d exported", seed.name, len(items), ok)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("wrote %d posts to %s", len(rows), args.out)


if __name__ == "__main__":
    main()
