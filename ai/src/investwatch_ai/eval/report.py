"""Markdown report of a golden-set run (`docs/eval/latest.md`)."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..rules import load_rules, load_rules_file
from ..schemas import ModuleId
from .golden import SCRAPED_SOCIAL, GoldenItem
from .metrics import Confusion, best_threshold, confusion, sweep
from .run import Prediction

MODULES: tuple[ModuleId, ...] = ("m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory")
MAX_ERRORS = 12

Row = tuple[GoldenItem, Prediction]
Filter = Callable[[GoldenItem], bool]


@dataclass(frozen=True)
class RunInfo:
    """How the run was made (printed in the report header)."""

    mode: str
    model: str
    generated_at: str
    subset: str


def _f(x: float) -> str:
    return f"{x:.2f}"


def _table(header: list[str], rows: Iterable[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def _module_conf(rows: list[Row], module: ModuleId) -> Confusion:
    return confusion((i.label == 1, p.predicted) for i, p in rows if i.module == module)


def _metrics_table(rows: list[Row], train: list[Row]) -> list[str]:
    body = []
    for module in MODULES:
        c = _module_conf(rows, module)
        if c.n == 0:
            body.append([module, "0", *["-"] * 11])
            continue
        scored = [(p.score, i.label == 1) for i, p in train if i.module == module]
        curve = sweep(scored)
        threshold = next(p.threshold for i, p in rows if i.module == module)
        body.append(
            [
                module,
                str(c.n),
                str(c.positives),
                str(c.tp),
                str(c.fp),
                str(c.fn),
                str(c.tn),
                _f(c.precision),
                _f(c.recall),
                _f(c.f1),
                _f(c.f2),
                _f(threshold),
                f"{_f(best_threshold(curve, 1.0))} / {_f(best_threshold(curve, 2.0))}"
                if scored
                else "-",
            ]
        )
    return _table(
        [
            "module",
            "n",
            "pos",
            "TP",
            "FP",
            "FN",
            "TN",
            "precision",
            "recall",
            "F1",
            "F2",
            "threshold",
            "best F1 / F2 thr. (train)",
        ],
        body,
    )


def _confusion_matrices(rows: list[Row]) -> list[str]:
    out: list[str] = []
    for module in MODULES:
        c = _module_conf(rows, module)
        out += [
            f"**{module}** (n = {c.n})",
            "",
            *_table(
                ["", "predicted 1", "predicted 0"],
                [["label 1", str(c.tp), str(c.fn)], ["label 0", str(c.fp), str(c.tn)]],
            ),
            "",
        ]
    return out


def _rule_rows(rows: list[Row]) -> list[list[str]]:
    metas = load_rules()
    per_rule: dict[tuple[str, str], list[tuple[bool, bool]]] = defaultdict(list)
    unknown: Counter[tuple[str, str]] = Counter()
    for item, pred in rows:
        for rule_id, truth in item.rule_labels.items():
            got = pred.rules.get(rule_id)
            key: tuple[str, str] = (item.module, rule_id)
            per_rule[key].append((truth == "fail", got == "fail"))
            if got == "unknown":
                unknown[key] += 1

    def order(key: tuple[str, str]) -> tuple[str, int, str]:
        digits = "".join(ch for ch in key[1] if ch.isdigit())
        return key[0], int(digits or 0), key[1]

    out = []
    for key in sorted(per_rule, key=order):
        c = confusion(per_rule[key])
        name = metas[key[1]].name if key[1] in metas else ""
        out.append(
            [
                key[0][:2],
                key[1],
                name,
                str(c.n),
                str(c.positives),
                str(c.tp),
                str(c.fp),
                str(c.fn),
                str(c.tn),
                _f(c.precision) if c.tp + c.fp else "-",
                _f(c.recall) if c.positives else "-",
                _f(c.f1) if c.positives else "-",
                str(unknown[key]),
            ]
        )
    return out


def _rule_table(rows: list[Row]) -> list[str]:
    body = _rule_rows(rows)
    if not body:
        return ["_No per-rule labels in this selection._"]
    return _table(
        [
            "mod",
            "rule",
            "name",
            "n",
            "fail (label)",
            "TP",
            "FP",
            "FN",
            "TN",
            "precision",
            "recall",
            "F1",
            "unknown",
        ],
        body,
    )


def _counts(items: list[GoldenItem]) -> list[str]:
    counts: Counter[tuple[str, str, str, int]] = Counter(
        (i.module, i.origin, i.split, i.label) for i in items if not i.excluded
    )
    body = []
    for module in MODULES:
        for origin in ("synthetic", "real"):
            row = [counts[(module, origin, s, lab)] for s in ("train", "holdout") for lab in (1, 0)]
            if sum(row):
                body.append([module, origin, *map(str, row), str(sum(row))])
    return _table(
        ["module", "origin", "train +", "train -", "holdout +", "holdout -", "total"], body
    )


def _provenance(items: list[GoldenItem]) -> list[str]:
    counts: Counter[tuple[str, str, str, bool]] = Counter()
    for i in items:
        p = i.provenance
        counts[(p.collector, p.method, p.compliant, p.headline)] += 1
    body = [
        [col, method, compliant, "yes" if headline else "**no**", str(n)]
        for (col, method, compliant, headline), n in sorted(counts.items())
    ]
    return _table(["collector", "method", "compliant", "in headline", "items"], body)


def _labellers(items: list[GoldenItem]) -> list[str]:
    counts: Counter[tuple[str, str]] = Counter()
    for i in items:
        state = i.review.decision if i.review else "not reviewed"
        counts[(i.labeler, state)] += 1
    body = [[lab, state, str(n)] for (lab, state), n in sorted(counts.items())]
    return _table(["labeler", "human review", "items"], body)


def _errors(rows: list[Row]) -> list[str]:
    out: list[str] = []
    for module in MODULES:
        wrong = [(i, p) for i, p in rows if i.module == module and (i.label == 1) != p.predicted]
        if not wrong:
            continue
        out.append(f"**{module}**")
        out.append("")
        for item, pred in wrong[:MAX_ERRORS]:
            kind = "FN" if item.label == 1 else "FP"
            out.append(
                f"- {kind} `{item.id}` score {pred.score:.2f} "
                f"({item.provenance.method}): {item.note[:110]}"
            )
        if len(wrong) > MAX_ERRORS:
            out.append(f"- ... and {len(wrong) - MAX_ERRORS} more")
        out.append("")
    return out


def _timing(rows: list[Row]) -> list[str]:
    body = []
    for module in (*MODULES, None):
        ms = sorted(p.ms for i, p in rows if module is None or i.module == module)
        if not ms:
            continue
        p95 = ms[min(len(ms) - 1, round(0.95 * (len(ms) - 1)))]
        body.append(
            [
                module or "all",
                str(len(ms)),
                f"{statistics.fmean(ms):.1f}",
                f"{statistics.median(ms):.1f}",
                f"{p95:.1f}",
                f"{ms[-1]:.1f}",
                str(sum(p.used_llm for i, p in rows if module is None or i.module == module)),
            ]
        )
    return _table(["module", "items", "mean ms", "p50 ms", "p95 ms", "max ms", "used LLM"], body)


def is_headline(item: GoldenItem) -> bool:
    """Compliant sources only (no scraped social-media items)."""
    return item.provenance.headline


def build_report(items: list[GoldenItem], preds: list[Prediction], info: RunInfo) -> str:
    """Render the full Markdown report."""
    by_id = {p.item_id: p for p in preds}
    rows: list[Row] = [(i, by_id[i.id]) for i in items if i.id in by_id]

    def pick(*filters: Filter) -> list[Row]:
        return [(i, p) for i, p in rows if all(f(i) for f in filters)]

    def holdout(i: GoldenItem) -> bool:
        return i.split == "holdout"

    def train(i: GoldenItem) -> bool:
        return i.split == "train"

    headline = pick(holdout, is_headline)
    train_headline = pick(train, is_headline)
    used = [i for i, _ in rows]
    n_no_text = sum(not i.excluded and i.id not in by_id for i in items)
    n_excluded = sum(i.excluded for i in items)
    n_scraped = sum(not is_headline(i) for i in used)
    n_human = sum(i.review is not None and i.labeler == "human" for i in used)
    n_agent_review = sum(i.review is not None and i.labeler == "agent" for i in items)
    reviewers = sorted({i.review.by for i in items if i.review and i.labeler == "agent"})
    n_agent = sum(i.origin == "real" and i.labeler == "agent" for i in used)
    n_rule = sum(i.origin == "real" and i.labeler == "rule" for i in used)
    rules_version = load_rules_file().version
    lines = [
        "# Golden-set evaluation",
        "",
        f"Generated by `make eval` on {info.generated_at}; analysis mode `{info.mode}`, "
        f"rules `{rules_version}`, model `{info.model}`. Subset: {info.subset}.",
        "",
        f"**Honest summary.** {len(used)} items ({sum(i.origin == 'synthetic' for i in used)} "
        f"synthetic or demo pages with labels known by construction, "
        f"{sum(i.origin == 'real' for i in used)} real public posts). Real items were "
        f"labelled by AI agents following the written rules in `docs/eval/LABELING.md` "
        f"({n_agent} items) or by a documented rule over an official source such as the KNF "
        f"warning list ({n_rule} items). {n_agent_review} hold-out items were re-reviewed by an "
        f"agent consensus ({', '.join(reviewers) or 'none'}: three blind model reviewers with "
        "different lenses, split cases adjudicated by a fourth; their verdict replaces the "
        f"label, see `docs/eval/LABELING.md`); {n_human} items carry a human review. "
        "These are our "
        "labels, not UKNF's. Headline numbers use only the **hold-out split** (40%, split by "
        f"domain / author / firm) and only **compliant sources**: {n_scraped} items collected "
        f"by scraping social platforms ({', '.join(sorted(SCRAPED_SOCIAL))}) are excluded and "
        f"reported separately below. Not scored: {n_no_text} items whose text is not "
        f"available (withdrawn or waiting for an official API fetch) and {n_excluded} items "
        "excluded by a reviewer.",
        "",
        "## Headline: hold-out, compliant sources",
        "",
        *_metrics_table(headline, train_headline),
        "",
        "Thresholds are the service's: `THRESHOLD_M1..M3` when set, else the ones `make train` "
        "chose by train-split cross-validation (F2), else 0.5 / 0.6 / 0.5. The last column is "
        "the threshold that maximises F1 / F2 on the **train** split (never tuned on "
        "hold-out); for M1 / M3 with the heads on it is in-sample (the heads were fitted on "
        "those items), so read the train-CV table instead.",
        "",
        "### Confusion matrices (hold-out, compliant)",
        "",
        *_confusion_matrices(headline),
        "### Per-rule metrics (hold-out, compliant)",
        "",
        "Only rules with a known verdict are scored; `fail` is the positive class (for the "
        "art. 76 elements `fail` = element present). `unknown` = the rule could not be "
        "evaluated (e.g. a render rule without a render snapshot).",
        "",
        *_rule_table(headline),
        "",
        "### Per-rule metrics (all splits, compliant)",
        "",
        "Rules are hand-written, not fitted, so the train split is a fair extra sample here.",
        "",
        *_rule_table(pick(is_headline)),
        "",
        "## Breakdowns",
        "",
        "### Hold-out, synthetic and demo pages only",
        "",
        *_metrics_table(
            pick(holdout, is_headline, lambda i: i.origin == "synthetic"),
            pick(train, is_headline, lambda i: i.origin == "synthetic"),
        ),
        "",
        "### Hold-out, real compliant items only",
        "",
        *_metrics_table(
            pick(holdout, is_headline, lambda i: i.origin == "real"),
            pick(train, is_headline, lambda i: i.origin == "real"),
        ),
        "",
        "### Hold-out, all sources (including scraped social items; not a headline number)",
        "",
        *_metrics_table(pick(holdout), pick(train)),
        "",
        "### Train split, compliant (sanity check)",
        "",
        *_metrics_table(train_headline, train_headline),
        "",
        "## Dataset",
        "",
        "### Items by module, origin, split and label",
        "",
        *_counts(used),
        "",
        "### Items by provenance",
        "",
        *_provenance(used),
        "",
        "### Who labelled",
        "",
        *_labellers(used),
        "",
        "## Errors on the hold-out split (compliant)",
        "",
        *(_errors(headline) or ["_None._", ""]),
        "## Timing",
        "",
        "Wall time of `analyze()` per item in this process (rules, render checks, scoring; no "
        "network unless the mode is `llm`).",
        "",
        *_timing(rows),
        "",
    ]
    return "\n".join(lines)
