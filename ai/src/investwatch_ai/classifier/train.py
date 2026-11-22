"""`make train`: fit the M1 / M3 heads and choose module thresholds on the TRAIN split only.

Usage (from `ai/`; Ollama with bge-m3 for the embedding variant, else lexicon only):
    uv run python -m investwatch_ai.classifier.train [--no-extra] [--no-embed]

Data: golden items with `split == "train"` from compliant sources, plus train-only extra
texts (`data/golden/synthetic/haiku_v1.jsonl`, provenance `generator:haiku`, and
`data/golden/augment/*.jsonl`, provenance `generator:llm`). The hold-out split is never
read here. Everything is seeded; the same inputs give byte-identical weights.

Per head and variant: L2 logistic regression, C picked by grouped stratified 5-fold CV
(log loss), Platt scaling fitted on the out-of-fold decision values, threshold = the F2
optimum of the calibrated out-of-fold probabilities. M2 has no head; its threshold is the
F2 optimum of the rule score on the train split.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import StratifiedGroupKFold

from ..analyze import EMBED_MAX_CHARS
from ..config import Settings, get_settings
from ..eval.golden import GoldenItem
from ..eval.metrics import at_threshold, best_threshold, sweep
from ..eval.run import item_text, load_golden, predict, to_request
from ..llm import OllamaClient
from ..preprocess import clean_text, detect_lang
from ..rules import M1_RULE_IDS, M3_ELEMENT_IDS, RuleContext, evaluate
from ..schemas import ModuleId
from .embcache import EmbeddingCache
from .features import HeadId, extract, feature_names
from .model import (
    WEIGHTS_DIR,
    HeadWeights,
    ThresholdsFile,
    VariantWeights,
    dump,
)

log = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[4]
GOLDEN = REPO / "data" / "golden"
EXTRA_FILES = (
    GOLDEN / "synthetic" / "haiku_v1.jsonl",
    GOLDEN / "augment" / "llm_train.jsonl",
)
SEED = 20261121
VERSION = "lr-v1"
C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0)
FOLDS = 5
HEADS: tuple[HeadId, ...] = ("m1_third_party_ad", "m3_shadow_advisory")
SHORT: dict[str, ModuleId] = {
    "m1": "m1_third_party_ad",
    "m2": "m2_risk_disclosure",
    "m3": "m3_shadow_advisory",
}


@dataclass
class Row:
    """One training example of a head."""

    id: str
    label: int
    group: str
    source: str
    """golden | generator:haiku | generator:llm"""
    features: dict[str, float]
    text: str


def _context(text: str, item: GoldenItem | None) -> RuleContext:
    if item is None:
        return RuleContext.build(text, lang="pl")
    req = to_request(GOLDEN, item)
    owner = next((m for m in req.firm_matches if m.on == "author"), None)
    mention = max(
        (m for m in req.firm_matches if m.on == "content"),
        key=lambda m: m.confidence,
        default=None,
    )
    primary = owner or mention
    return RuleContext.build(
        text,
        firm=primary.firm if primary else None,
        render=req.render,
        lang=item.post.lang or detect_lang(text),
    )


def _features(head: HeadId, text: str, item: GoldenItem | None) -> dict[str, float]:
    ctx = _context(text, item)
    ids = M1_RULE_IDS if head == "m1_third_party_ad" else M3_ELEMENT_IDS
    return extract(head, ctx, evaluate(ctx, ids))


def _routes_to(head: HeadId, item: GoldenItem) -> bool:
    """Would `analyze()` ever apply this head to the item? (else the router decides alone)."""
    author = any(m.on == "author" for m in item.firm_matches)
    if head == "m1_third_party_ad":
        return not author and any(m.on == "content" for m in item.firm_matches)
    status = item.register_status or ("registered" if author else "not_registered")
    return status != "registered"


def golden_rows(head: HeadId, items: list[GoldenItem]) -> list[Row]:
    """Train-split, compliant golden items of the head's module that reach the head.

    Items labelled only by a list rule (`labeler == "rule"`: on the KNF warning list, so
    M3 = 1) are left out: the agent review of the hold-out found that rule wrong for most
    pages, whose visible text shows brokerage, not advice.
    """
    rows = []
    for item in items:
        if (
            item.module != head
            or item.split != "train"
            or item.excluded
            or not item.provenance.headline
            or item.labeler == "rule"
            or not _routes_to(head, item)
        ):
            continue
        text = clean_text(item_text(GOLDEN, item))
        if not text.strip():
            continue
        rows.append(
            Row(item.id, item.label, item.group, "golden", _features(head, text, item), text)
        )
    return rows


def extra_rows(head: HeadId, files: tuple[Path, ...]) -> list[Row]:
    """Train-only synthetic texts (never in the golden set or any reported hold-out)."""
    rows = []
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            module = SHORT.get(d["module"], d["module"])
            if module != head or d.get("split", "train") != "train":
                continue
            prov = d.get("provenance")
            source = prov.get("collector", "generator") if isinstance(prov, dict) else str(prov)
            text = clean_text(d["text"])
            # LLM batches share style: keep a whole generator stratum inside one fold.
            group = f"{source}:{d.get('spec') or d['id'].rsplit('-', 1)[0]}"
            rows.append(
                Row(d["id"], int(d["label"]), group, source, _features(head, text, None), text)
            )
    return rows


def _matrix(head: HeadId, rows: list[Row], embeddings: list[list[float]] | None) -> np.ndarray:
    names = feature_names(head)
    x = np.array([[r.features[n] for n in names] for r in rows], dtype=np.float64)
    if embeddings is not None:
        x = np.hstack([x, np.asarray(embeddings, dtype=np.float64)])
    return x


def _standardise(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    return (x - mean) / scale, mean, scale


def _lr(c: float) -> LogisticRegression:
    return LogisticRegression(C=c, max_iter=5000, class_weight="balanced", random_state=SEED)


def _oof_decision(x: np.ndarray, y: np.ndarray, groups: list[str], c: float) -> np.ndarray:
    folds = StratifiedGroupKFold(n_splits=FOLDS, shuffle=True, random_state=SEED)
    out = np.zeros(len(y))
    for tr, te in folds.split(x, y, groups):
        xs, mean, scale = _standardise(x[tr])
        model = _lr(c).fit(xs, y[tr])
        out[te] = model.decision_function((x[te] - mean) / scale)
    return out


def _platt(decision: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    cal = LogisticRegression(C=1e6, max_iter=5000).fit(decision.reshape(-1, 1), y)
    return float(cal.coef_[0][0]), float(cal.intercept_[0])


def fit_variant(
    head: HeadId, rows: list[Row], embeddings: list[list[float]] | None
) -> VariantWeights:
    """Pick C by CV, calibrate on out-of-fold scores, choose the F2 threshold, refit on all."""
    x = _matrix(head, rows, embeddings)
    y = np.array([r.label for r in rows])
    groups = [r.group for r in rows]
    best: tuple[float, float, np.ndarray] | None = None
    for c in C_GRID:
        d = _oof_decision(x, y, groups, c)
        a, b = _platt(d, y)
        p = 1 / (1 + np.exp(-(a * d + b)))
        loss = log_loss(y, p, labels=[0, 1])
        if best is None or loss < best[0] - 1e-9:
            best = (loss, c, d)
    assert best is not None
    loss, c, d = best
    a, b = _platt(d, y)
    p = 1 / (1 + np.exp(-(a * d + b)))
    scored = [(float(s), bool(t)) for s, t in zip(p, y, strict=True)]
    threshold = best_threshold(sweep(scored), beta=2.0)
    cv_all = at_threshold(scored, threshold)
    golden = [s for s, r in zip(scored, rows, strict=True) if r.source == "golden"]
    cv_golden = at_threshold(golden, threshold)
    xs, mean, scale = _standardise(x)
    model = _lr(c).fit(xs, y)
    coef = model.coef_[0]
    k = len(feature_names(head))
    return VariantWeights(
        features=list(feature_names(head)),
        mean=mean[:k].tolist(),
        scale=scale[:k].tolist(),
        coef=coef[:k].tolist(),
        intercept=float(model.intercept_[0]),
        emb_mean=mean[k:].tolist(),
        emb_scale=scale[k:].tolist(),
        emb_coef=coef[k:].tolist(),
        platt_a=a,
        platt_b=b,
        c=c,
        threshold=threshold,
        cv={
            "log_loss": loss,
            "brier": float(np.mean((p - y) ** 2)),
            "f1": cv_all.f1,
            "f2": cv_all.f2,
            "precision": cv_all.precision,
            "recall": cv_all.recall,
            "golden_f1": cv_golden.f1,
            "golden_f2": cv_golden.f2,
            "golden_n": float(cv_golden.n),
        },
    )


def m2_threshold(items: list[GoldenItem], settings: Settings) -> float:
    """F2-optimal threshold of the M2 rule score on the train split (compliant)."""
    plain = settings.model_copy(update={"classifier": False})
    scored = []
    for item in items:
        if (
            item.module != "m2_risk_disclosure"
            or item.split != "train"
            or item.excluded
            or not item.provenance.headline
            or not item_text(GOLDEN, item).strip()
        ):
            continue
        pred = predict(GOLDEN, item, plain)
        scored.append((pred.score, item.label == 1))
    return best_threshold(sweep(scored), beta=2.0, default=0.6)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=WEIGHTS_DIR)
    parser.add_argument("--no-extra", action="store_true", help="golden train items only")
    parser.add_argument("--no-embed", action="store_true", help="lexicon variant only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    items = load_golden(GOLDEN / "golden.jsonl")
    cache = EmbeddingCache(GOLDEN / "cache" / f"emb-{settings.embed_model}.jsonl")
    client = None if args.no_embed else OllamaClient(settings.ollama_url, timeout_s=300.0)
    if client is not None and not client.ping():
        log.warning("Ollama unreachable at %s: lexicon variant only", settings.ollama_url)
        client = None
    args.out.mkdir(parents=True, exist_ok=True)
    thresholds: dict[ModuleId, float] = {}
    for head in HEADS:
        rows = golden_rows(head, items)
        if not args.no_extra:
            rows += extra_rows(head, EXTRA_FILES)
        counts: dict[str, int] = {"rows": len(rows), "positives": sum(r.label for r in rows)}
        for r in rows:
            counts[r.source] = counts.get(r.source, 0) + 1
        variants = {"lexicon": fit_variant(head, rows, None)}
        vectors = cache.get_many(
            [r.text[:EMBED_MAX_CHARS] for r in rows], client, settings.embed_model
        )
        if all(v is not None for v in vectors):
            variants["embedding"] = fit_variant(head, rows, vectors)  # type: ignore[arg-type]
        weights = HeadWeights(
            module=head,
            version=VERSION,
            seed=SEED,
            embed_model=settings.embed_model,
            trained_on=counts,
            variants=variants,
        )
        dump(weights, args.out / f"{head}.json")
        thresholds[head] = weights.threshold
        for name, v in variants.items():
            log.info(
                "%s/%s: n=%d C=%g thr=%.2f cv F1=%.2f F2=%.2f golden F2=%.2f",
                head,
                name,
                len(rows),
                v.c,
                v.threshold,
                v.cv["f1"],
                v.cv["f2"],
                v.cv["golden_f2"],
            )
    thresholds["m2_risk_disclosure"] = m2_threshold(items, settings)
    log.info("m2 threshold (train F2): %.2f", thresholds["m2_risk_disclosure"])
    (args.out / "thresholds.json").write_text(
        ThresholdsFile(
            thresholds=dict(sorted(thresholds.items())),
            method="F2 optimum on the train split (heads: calibrated out-of-fold CV)",
        ).model_dump_json(indent=2)
        + "\n",
        encoding="utf-8",
    )
    log.info("wrote %s (%s)", args.out, datetime.now(UTC).isoformat(timespec="seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
