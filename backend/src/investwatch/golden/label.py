"""Confirm golden-set labels quickly, in the terminal or through a CSV sheet.

Usage: `make label BY=<github-login>` or, from `backend/`:
    uv run python -m investwatch.golden.label --by mkosowski             # interactive
    uv run python -m investwatch.golden.label --status                    # progress only
    uv run python -m investwatch.golden.label --export-csv sheet.csv      # for a spreadsheet
    uv run python -m investwatch.golden.label --import-csv sheet.csv --by mkosowski

Keys in the interactive mode: Enter/a = accept, 0/1 = set the label, x = exclude,
s = skip, q = quit. Every decision is written to `golden.jsonl` at once. Rules:
`docs/eval/LABELING.md`.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import textwrap
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from investwatch.golden.build import REPO, load_items, save_items
from investwatch.golden.real import resolve_text
from investwatch.golden.schemas import GoldenItem, Labeler, Review

Decision = Literal["accepted", "changed", "excluded"]

TEXT_PREVIEW = 1800
CSV_FIELDS = [
    "id",
    "module",
    "split",
    "method",
    "url",
    "author",
    "label",
    "labeler",
    "note",
    "decision",
    "new_label",
    "comment",
    "text",
]
"""Fill `decision` (accept / change / exclude) and, for `change`, `new_label` (0 or 1)."""


def golden_path() -> Path:
    """`data/golden/golden.jsonl` of this checkout (or `$GOLDEN_DIR`)."""
    return Path(os.environ.get("GOLDEN_DIR", REPO / "data" / "golden")) / "golden.jsonl"


def select(
    items: Iterable[GoldenItem],
    *,
    split: str,
    module: str | None,
    include_scraped: bool,
    reviewed: bool,
) -> list[GoldenItem]:
    """Items to show: by split and module, unreviewed unless asked, headline sources only."""
    out = []
    for item in items:
        if split != "all" and item.split != split:
            continue
        if module and not item.module.startswith(module):
            continue
        if not include_scraped and not item.provenance.headline:
            continue
        if not reviewed and item.review is not None:
            continue
        out.append(item)
    return out


def apply_decision(
    item: GoldenItem,
    decision: Decision,
    by: str,
    new_label: int | None = None,
    comment: str = "",
    labeler: Labeler = "human",
) -> GoldenItem:
    """Return the item with a review recorded (label changed for `changed`).

    `labeler` says who reviewed: `human` for a person, `agent` for an AI review (e.g. a
    consensus of several models, named in `by`), so reports never count it as human.
    """
    label: int = item.label
    if decision == "changed":
        if new_label not in (0, 1):
            raise ValueError("a changed label must be 0 or 1")
        label = new_label
    review = Review(
        by=by,
        at=datetime.now(UTC).isoformat(timespec="seconds"),
        decision=decision,
        previous_label=item.label if label != item.label else None,
    )
    note = f"{item.note} | review: {comment}" if comment else item.note
    return item.model_copy(
        update={
            "label": label,
            "review": review,
            "labeler": labeler,
            "confidence": 1.0 if decision != "excluded" else item.confidence,
            "note": note,
        }
    )


def status(items: list[GoldenItem]) -> str:
    """Review progress per split and module (headline sources only)."""
    counts: Counter[tuple[str, str, str]] = Counter()
    for item in items:
        if not item.provenance.headline:
            continue
        state = item.review.decision if item.review else "pending"
        counts[(item.split, item.module, state)] += 1
    lines = ["split     module                 accepted changed excluded pending"]
    for split in ("holdout", "train"):
        for module in sorted({i.module for i in items}):
            row = [counts[(split, module, s)] for s in ("accepted", "changed", "excluded")]
            pending = counts[(split, module, "pending")]
            lines.append(
                f"{split:<9} {module:<22} {row[0]:>8} {row[1]:>7} {row[2]:>8} {pending:>7}"
            )
    return "\n".join(lines)


def _show(item: GoldenItem, text: str, index: int, total: int) -> str:
    rules = " ".join(f"{k}={v}" for k, v in sorted(item.rule_labels.items()))
    body = textwrap.shorten(" ".join(text.split()), TEXT_PREVIEW, placeholder=" [...]")
    return "\n".join(
        [
            "",
            "=" * 78,
            f"[{index}/{total}] {item.id}  {item.module}  split={item.split}",
            f"source: {item.provenance.collector} / {item.provenance.method}  group={item.group}",
            f"url:    {item.post.url}",
            f"author: {item.post.author}  register={item.register_status}",
            f"label:  {item.label}  (by {item.labeler}, confidence {item.confidence:.2f})"
            + (f"  rules: {rules}" if rules else ""),
            f"note:   {item.note}",
            "-" * 78,
            textwrap.fill(body, 78),
            "-" * 78,
        ]
    )


def interactive(
    path: Path,
    by: str,
    chosen: list[GoldenItem],
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> int:
    """Walk through `chosen`, saving each decision; return the number of decisions."""
    root = path.parent
    done = 0
    for n, item in enumerate(chosen, start=1):
        out(_show(item, resolve_text(root, item), n, len(chosen)))
        while True:
            key = ask("[Enter/a] accept  [0/1] set label  [x] exclude  [s] skip  [q] quit > ")
            key = key.strip().lower()
            if key in ("", "a"):
                updated = apply_decision(item, "accepted", by)
            elif key in ("0", "1"):
                same = int(key) == item.label
                updated = apply_decision(item, "accepted" if same else "changed", by, int(key))
            elif key == "x":
                updated = apply_decision(item, "excluded", by, comment=ask("reason > ").strip())
            elif key == "s":
                updated = None
            elif key == "q":
                return done
            else:
                continue
            break
        if updated is not None:
            items = {i.id: i for i in load_items(path)}
            items[updated.id] = updated
            save_items(path, list(items.values()))
            done += 1
    return done


def export_csv(target: Path, chosen: list[GoldenItem], root: Path) -> None:
    """Write a sheet for spreadsheet labelling."""
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in chosen:
            writer.writerow(
                {
                    "id": item.id,
                    "module": item.module,
                    "split": item.split,
                    "method": item.provenance.method,
                    "url": item.post.url,
                    "author": item.post.author,
                    "label": item.label,
                    "labeler": item.labeler,
                    "note": item.note,
                    "decision": "",
                    "new_label": "",
                    "comment": "",
                    "text": " ".join(resolve_text(root, item).split())[:4000],
                }
            )


def import_csv(source: Path, path: Path, by: str, labeler: Labeler = "human") -> int:
    """Apply filled-in rows of a sheet; return the number of decisions applied."""
    items = {i.id: i for i in load_items(path)}
    decisions: dict[str, Decision] = {
        "accept": "accepted",
        "change": "changed",
        "exclude": "excluded",
    }
    applied = 0
    with source.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            decision = decisions.get(row.get("decision", "").strip().lower())
            if decision is None or row["id"] not in items:
                continue
            new_label = int(row["new_label"]) if row.get("new_label", "").strip() else None
            items[row["id"]] = apply_decision(
                items[row["id"]],
                decision,
                by,
                new_label,
                row.get("comment", "").strip(),
                labeler,
            )
            applied += 1
    save_items(path, list(items.values()))
    return applied


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--by", help="reviewer (GitHub login); required to record decisions")
    parser.add_argument("--split", default="holdout", choices=["holdout", "train", "all"])
    parser.add_argument("--module", help="m1, m2 or m3 (prefix of the module id)")
    parser.add_argument("--include-scraped", action="store_true", help="also non-headline items")
    parser.add_argument("--reviewed", action="store_true", help="also already reviewed items")
    parser.add_argument("--status", action="store_true", help="print progress and exit")
    parser.add_argument("--export-csv", type=Path)
    parser.add_argument("--import-csv", type=Path)
    parser.add_argument(
        "--labeler",
        choices=["human", "agent"],
        default="human",
        help="who made the imported decisions (agent = AI review, never reported as human)",
    )
    args = parser.parse_args(argv)

    path = golden_path()
    items = load_items(path)
    if args.status:
        print(status(items))
        return
    if args.import_csv:
        if not args.by:
            parser.error("--by is required with --import-csv")
        applied = import_csv(args.import_csv, path, args.by, args.labeler)
        print(f"applied {applied} decisions")
        return
    chosen = select(
        items,
        split=args.split,
        module=args.module,
        include_scraped=args.include_scraped,
        reviewed=args.reviewed,
    )
    if args.export_csv:
        export_csv(args.export_csv, chosen, path.parent)
        print(f"wrote {len(chosen)} rows to {args.export_csv}")
        return
    if not args.by:
        parser.error("--by is required to record decisions")
    if not sys.stdin.isatty():
        parser.error("interactive mode needs a terminal; use --export-csv / --import-csv")
    done = interactive(path, args.by, chosen)
    print(f"recorded {done} decisions\n{status(load_items(path))}")


if __name__ == "__main__":
    main()
