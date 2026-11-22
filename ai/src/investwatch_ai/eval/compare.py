"""Compare several evaluation runs (before / after, ablations) on the same golden set.

Usage (from `ai/`), after writing one predictions file per configuration with
`python -m investwatch_ai.eval --predictions <file> ...`:

    uv run python -m investwatch_ai.eval.compare --run "rules=a.jsonl" --run "heads=b.jsonl" \
        --report ../docs/eval/latest.md --notes ../docs/eval/notes.md

The section is inserted between the markers below (replacing an older one), so the rest of
`latest.md` written by `make eval` stays as it is. Only hold-out, compliant items are scored.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..classifier.model import WEIGHTS_DIR, HeadWeights
from ..rules import load_rules
from .golden import GoldenItem
from .metrics import Confusion, bootstrap_ci, confusion
from .report import MODULES, is_headline
from .run import Prediction, load_golden

START = "<!-- comparison:start -->"
END = "<!-- comparison:end -->"
REPO = Path(__file__).resolve().parents[4]
log = logging.getLogger(__name__)

Run = tuple[str, dict[str, Prediction]]


def _f(x: float) -> str:
    return f"{x:.2f}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return out + ["| " + " | ".join(r) + " |" for r in rows]


def load_run(path: Path) -> dict[str, Prediction]:
    """Predictions keyed by item id."""
    rows = [
        Prediction.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {p.item_id: p for p in rows}


def _holdout(items: list[GoldenItem]) -> list[GoldenItem]:
    return [i for i in items if i.split == "holdout" and is_headline(i) and not i.excluded]


def _pairs(
    items: list[GoldenItem], preds: dict[str, Prediction], module: str
) -> list[tuple[bool, bool]]:
    return [
        (i.label == 1, preds[i.id].predicted) for i in items if i.module == module and i.id in preds
    ]


def module_table(items: list[GoldenItem], runs: list[Run]) -> list[str]:
    """Per configuration and module: counts, P / R / F1 with a 95% bootstrap CI, F2."""
    body = []
    for module in MODULES:
        for name, preds in runs:
            pairs = _pairs(items, preds, module)
            c = confusion(pairs)
            if c.n == 0:
                continue
            lo, hi = bootstrap_ci(pairs, lambda k: k.f1)
            thr = next(preds[i.id].threshold for i in items if i.module == module and i.id in preds)
            body.append(
                [
                    module,
                    name,
                    str(c.n),
                    str(c.positives),
                    f"{c.tp}/{c.fp}/{c.fn}/{c.tn}",
                    _f(c.precision),
                    _f(c.recall),
                    f"**{_f(c.f1)}** [{_f(lo)}, {_f(hi)}]",
                    _f(c.f2),
                    _f(thr),
                ]
            )
    return _table(
        [
            "module",
            "configuration",
            "n",
            "pos",
            "TP/FP/FN/TN",
            "P",
            "R",
            "F1 [95% CI]",
            "F2",
            "thr.",
        ],
        body,
    )


def ablation_table(items: list[GoldenItem], runs: list[Run]) -> list[str]:
    """Compact F1 / F2 grid: one row per configuration, one column pair per module."""
    body = []
    for name, preds in runs:
        row = [name]
        for module in MODULES:
            c = confusion(_pairs(items, preds, module))
            row.append(f"{_f(c.f1)} / {_f(c.f2)}" if c.n else "-")
        body.append(row)
    return _table(["configuration", *(f"{m.split('_')[0]} F1 / F2" for m in MODULES)], body)


def rule_table(items: list[GoldenItem], runs: list[Run]) -> list[str]:
    """Per-rule F1 on the hold-out (fail = positive) for each configuration."""
    metas = load_rules()
    keys = sorted(
        {(i.module, r) for i in items for r, v in i.rule_labels.items() if v != "na"},
        key=lambda k: (k[0], len(k[1]), k[1]),
    )
    body = []
    for module, rule_id in keys:
        row = [module.split("_")[0], rule_id, metas[rule_id].name if rule_id in metas else ""]
        n = 0
        for _, preds in runs:
            pairs = []
            for i in items:
                label = i.rule_labels.get(rule_id)
                p = preds.get(i.id)
                if i.module != module or label in (None, "na") or p is None:
                    continue
                status = p.rules.get(rule_id)
                if status is None or status == "unknown":
                    continue
                pairs.append((label == "fail", status == "fail"))
            c: Confusion = confusion(pairs)
            n = max(n, c.n)
            row.append(f"{_f(c.f1)} ({c.tp}/{c.fp}/{c.fn})" if c.positives or c.fp else "-")
        body.append([*row[:3], str(n), *row[3:]])
    return _table(["mod", "rule", "name", "n", *(f"{n} F1 (TP/FP/FN)" for n, _ in runs)], body)


def heads_table(weights_dir: Path) -> list[str]:
    """Train-split cross-validation of the heads, from the committed weights."""
    body = []
    for module in ("m1_third_party_ad", "m3_shadow_advisory"):
        path = weights_dir / f"{module}.json"
        if not path.exists():
            continue
        head = HeadWeights.model_validate_json(path.read_text(encoding="utf-8"))
        rows = ", ".join(f"{k} {v}" for k, v in head.trained_on.items())
        for name, v in head.variants.items():
            body.append(
                [
                    module,
                    name,
                    rows,
                    f"{v.c:g}",
                    _f(v.threshold),
                    _f(v.cv["f1"]),
                    _f(v.cv["f2"]),
                    _f(v.cv["brier"]),
                    f"{_f(v.cv['golden_f2'])} (n={int(v.cv['golden_n'])})",
                ]
            )
    return _table(
        [
            "head",
            "variant",
            "training rows",
            "C",
            "thr. (F2)",
            "OOF F1",
            "OOF F2",
            "Brier",
            "OOF F2 golden only",
        ],
        body,
    )


def section(items: list[GoldenItem], runs: list[Run], weights_dir: Path, notes: str | None) -> str:
    """The comparison section in Markdown."""
    hold = _holdout(items)
    lines = [
        START,
        "## Before / after and ablation (hold-out, compliant)",
        "",
        "Every configuration is scored on the same hold-out items (never used for training, "
        "rule fixes or thresholds). Intervals are 95% percentile bootstrap over items "
        "(2000 resamples, fixed seed); with this few positives they are wide, and overlapping "
        "intervals mean the difference is not established.",
        "",
        "Configurations: " + "; ".join(f"`{name}`" for name, _ in runs) + ".",
        "",
        "### Summary (F1 / F2 per module)",
        "",
        *ablation_table(hold, runs),
        "",
        "### Per module with confidence intervals",
        "",
        *module_table(hold, runs),
        "",
        "### Per rule (hold-out; fail = positive)",
        "",
        *rule_table(hold, runs),
        "",
        "### Classifier heads: train-split cross-validation",
        "",
        "Out-of-fold (grouped, stratified 5-fold) on the train split plus train-only synthetic "
        "texts. `golden only` restricts the same out-of-fold scores to golden train items.",
        "",
        *heads_table(weights_dir),
        "",
    ]
    if notes:
        lines += [notes.rstrip(), ""]
    lines.append(END)
    return "\n".join(lines) + "\n"


def insert(report: str, block: str) -> str:
    """Replace an existing comparison block, or insert it after the headline section."""
    if START in report and END in report:
        head, _, rest = report.partition(START)
        _, _, tail = rest.partition(END)
        return head + block.rstrip("\n") + tail
    marker = "\n## Breakdowns"
    if marker in report:
        head, _, tail = report.partition(marker)
        return head + "\n" + block + marker + tail
    return report + "\n" + block


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", type=Path, default=REPO / "data" / "golden")
    parser.add_argument("--run", action="append", required=True, help="name=predictions.jsonl")
    parser.add_argument("--report", type=Path, default=REPO / "docs" / "eval" / "latest.md")
    parser.add_argument("--notes", type=Path, default=None)
    parser.add_argument("--weights", type=Path, default=WEIGHTS_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    items = load_golden(args.golden_dir / "golden.jsonl")
    runs: list[Run] = []
    for spec in args.run:
        name, _, path = spec.partition("=")
        runs.append((name, load_run(Path(path))))
    notes = args.notes.read_text(encoding="utf-8") if args.notes else None
    block = section(items, runs, args.weights, notes)
    report = args.report.read_text(encoding="utf-8") if args.report.exists() else ""
    args.report.write_text(insert(report, block), encoding="utf-8")
    log.info("wrote comparison of %d runs into %s", len(runs), args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
