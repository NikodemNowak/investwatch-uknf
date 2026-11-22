"""Build `data/golden/golden.jsonl` from the synthetic generator and the labelled real posts.

Usage: `make golden` or, from `backend/`:
    uv run python -m investwatch.golden.build            # rebuild, keep existing renders
    uv run python -m investwatch.golden.build --render   # also re-render synthetic pages

Human reviews already in `golden.jsonl` survive a rebuild (matched by item id).
Rendering needs Playwright Chromium (`uv run playwright install chromium`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections import defaultdict
from pathlib import Path

from investwatch.collectors.html_text import html_to_text
from investwatch.config import get_settings
from investwatch.golden import demo, real, synth
from investwatch.golden.schemas import GoldenItem, Split
from investwatch.golden.sources import records

log = logging.getLogger(__name__)

HOLDOUT_SHARE = 0.4
REPO = Path(__file__).resolve().parents[4]


def golden_dir() -> Path:
    """`data/golden/` of this checkout."""
    return get_settings().data_dir / "golden"


def write_pages(root: Path) -> dict[str, str]:
    """Write the synthetic M2 pages; return item id -> visible text."""
    pages = root / "synthetic" / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = {}
    for i, spec in enumerate(synth.M2_PAGES):
        item_id = synth.m2_item_id(i)
        page = synth.render_page(spec)
        (pages / f"{item_id}.html").write_text(page, encoding="utf-8")
        texts[item_id] = html_to_text(page)
    return texts


def page_files(root: Path) -> dict[str, Path]:
    """Item id -> HTML file of every page that needs a render snapshot."""
    files = {
        synth.m2_item_id(i): root / "synthetic" / "pages" / f"{synth.m2_item_id(i)}.html"
        for i in range(len(synth.M2_PAGES))
    }
    for page in demo.PAGES:
        files[demo.item_id(page)] = demo.demo_root(REPO) / page.file
    return files


def render_pages(root: Path, files: dict[str, Path]) -> None:
    """Measure each page in three viewports with the production capture code."""
    from playwright.sync_api import sync_playwright

    from investwatch.render.capture import VIEWPORTS, capture

    out = root / "synthetic" / "render"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        context = browser.new_context(viewport=VIEWPORTS["desktop"], locale="pl-PL")
        page = context.new_page()
        for item_id, path in sorted(files.items()):
            # file:// so relative stylesheets (demo-sites/aurora.css) load as in production.
            page.goto(path.resolve().as_uri(), wait_until="load")
            snapshot, _ = capture(page)
            (out / f"{item_id}.json").write_text(
                snapshot.model_dump_json(exclude_none=True), encoding="utf-8"
            )
            log.info("rendered %s", item_id)
        browser.close()


def _hash01(key: str) -> float:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def assign_splits(items: list[GoldenItem], share: float = HOLDOUT_SHARE) -> list[GoldenItem]:
    """60/40 split by leakage group (domain, author or firm), deterministic.

    A group goes wholly to one side. Groups are stratified by (module, origin, headline
    eligibility, public-data source) so the compliant real items and every public source get
    their own 60/40, then ordered by a hash of their key and moved to hold-out until it holds
    `share` of the stratum's items. Items without a public source keep their earlier strata,
    so adding a source does not reshuffle existing items.
    """
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        groups[(item.module, item.group)].append(i)
    strata: dict[tuple[str, str, bool, str], list[tuple[str, str]]] = defaultdict(list)
    for key, members in groups.items():
        first = items[members[0]]
        base = (first.module, first.origin, first.provenance.headline)
        strata[(*base, first.provenance.source or "")].append(key)
    split: list[Split] = ["train"] * len(items)
    for stratum, keys in strata.items():
        total = sum(len(groups[k]) for k in keys)
        held = 0
        salt: tuple[object, ...] = stratum if stratum[3] else stratum[:3]
        for key in sorted(keys, key=lambda k: _hash01(f"{salt}|{k[1]}")):
            size = len(groups[key])
            if held >= share * total:
                break
            if held > 0 and held + size > share * total + 0.5 * size:
                continue
            for i in groups[key]:
                split[i] = "holdout"
            held += size
    return [item.model_copy(update={"split": s}) for item, s in zip(items, split, strict=True)]


def load_items(path: Path) -> list[GoldenItem]:
    """Read a golden JSONL file."""
    if not path.exists():
        return []
    return [
        GoldenItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save_items(path: Path, items: list[GoldenItem]) -> None:
    """Write a golden JSONL file, one item per line, stable order."""
    lines = [item.model_dump_json(exclude_defaults=False) for item in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def keep_reviews(new: list[GoldenItem], old: list[GoldenItem]) -> list[GoldenItem]:
    """Carry human reviews (and the human label) over to the rebuilt items."""
    reviewed = {o.id: o for o in old if o.review is not None}
    out: list[GoldenItem] = []
    for item in new:
        prev = reviewed.get(item.id)
        if prev is None:
            out.append(item)
            continue
        out.append(
            item.model_copy(
                update={
                    "label": prev.label,
                    "rule_labels": prev.rule_labels,
                    "labeler": prev.labeler,
                    "confidence": prev.confidence,
                    "review": prev.review,
                    "note": prev.note if " | review: " in prev.note else item.note,
                }
            )
        )
    return out


def build(root: Path, *, render: bool) -> list[GoldenItem]:
    """Assemble all items, assign splits and keep earlier human reviews."""
    texts = write_pages(root)
    files = page_files(root)
    if not render:
        files = {
            i: f
            for i, f in files.items()
            if not (root / "synthetic" / "render" / f"{i}.json").exists()
        }
    if files:
        render_pages(root, files)
    items = [
        *synth.m2_items(texts),
        *demo.demo_items(REPO),
        *synth.text_items(),
        *real.real_items(root),
        *records.public_items(root),
    ]
    items = assign_splits(items)
    path = root / "golden.jsonl"
    return keep_reviews(items, load_items(path))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="re-render all synthetic pages")
    args = parser.parse_args()
    # The registry snapshot and the golden files live in the repo's data/, not in backend/.
    os.environ.setdefault("APP_DATA_DIR", str(REPO / "data"))
    get_settings.cache_clear()
    logging.basicConfig(level=logging.INFO)
    root = golden_dir()
    items = build(root, render=args.render)
    save_items(root / "golden.jsonl", items)
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[f"{item.module}/{item.origin}/{item.split}/{item.label}"] += 1
    log.info("wrote %d items: %s", len(items), json.dumps(dict(sorted(counts.items()))))


if __name__ == "__main__":
    main()
