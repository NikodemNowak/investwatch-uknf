"""`make eval`: evaluate the golden set and write `docs/eval/latest.md`.

Usage (from `ai/`):
    uv run python -m investwatch_ai.eval                    # full set, rules mode
    uv run python -m investwatch_ai.eval --subset ci        # small stratified subset
    uv run python -m investwatch_ai.eval --mode llm         # with the Ollama review
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from ..classifier.embcache import EmbeddingCache
from ..config import Settings, get_settings
from ..llm import OllamaClient
from .golden import GoldenItem
from .report import RunInfo, build_report
from .run import embed_text, load_golden, run, warning_matches

REPO = Path(__file__).resolve().parents[4]
CI_PER_STRATUM = 3

log = logging.getLogger(__name__)


def ci_subset(items: list[GoldenItem], per_stratum: int = CI_PER_STRATUM) -> list[GoldenItem]:
    """A few items of every (module, origin, split, label) stratum, compliant sources only."""
    taken: dict[tuple[str, str, str, int], int] = {}
    out = []
    for item in items:
        if not item.provenance.headline:
            continue
        key = (item.module, item.origin, item.split, item.label)
        if taken.get(key, 0) < per_stratum:
            taken[key] = taken.get(key, 0) + 1
            out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", type=Path, default=REPO / "data" / "golden")
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "eval" / "latest.md")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="also write per-item scores as JSONL (default: <golden-dir>/predictions.jsonl "
        "for a full run, none for a subset); `seed` loads them into the labels table",
    )
    parser.add_argument("--subset", choices=["all", "ci"], default="all")
    parser.add_argument("--mode", choices=["rules", "llm"], default="rules")
    parser.add_argument(
        "--embed",
        action="store_true",
        help="embed items with bge-m3 (cached in data/golden/cache/) so the classifier heads "
        "use their embedding variant, as in production with Ollama up",
    )
    parser.add_argument(
        "--no-classifier", action="store_true", help="rules and lexicon only (ablation)"
    )
    parser.add_argument(
        "--warning-list",
        action="store_true",
        help="pass KNF warning-list matches to M3 (circular for items labelled from that list: "
        "never a headline number)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings: Settings = get_settings()
    if args.no_classifier:
        settings = settings.model_copy(update={"classifier": False})
    items = load_golden(args.golden_dir / "golden.jsonl")
    if args.subset == "ci":
        items = ci_subset(items)
    client = None
    if args.mode == "llm":
        client = OllamaClient(settings.ollama_url, timeout_s=settings.llm_timeout_s)
    embeddings: dict[str, list[float]] = {}
    if args.embed:
        cache = EmbeddingCache(args.golden_dir / "cache" / f"emb-{settings.embed_model}.jsonl")
        embed_client = client or OllamaClient(settings.ollama_url, timeout_s=300.0)
        texts = [embed_text(args.golden_dir, i) for i in items]
        vectors = cache.get_many(texts, embed_client, settings.embed_model)
        embeddings = {i.id: v for i, v in zip(items, vectors, strict=True) if v is not None}
    warnings = (
        warning_matches(items, REPO / "data" / "registry" / "knf_warnings.json")
        if args.warning_list
        else {}
    )
    t0 = time.perf_counter()
    preds = run(
        args.golden_dir,
        items,
        settings,
        mode=args.mode,
        client=client,
        embeddings=embeddings,
        warnings=warnings,
    )
    elapsed = time.perf_counter() - t0
    variant = (
        "rules only"
        if args.no_classifier
        else ("+classifier (bge-m3)" if args.embed else "+classifier (lexicon fallback)")
    ) + (" +KNF warning list" if args.warning_list else "")
    info = RunInfo(
        mode=f"{args.mode}, {variant}",
        model=settings.llm_model if args.mode == "llm" else "none",
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        subset=f"{args.subset} ({len(preds)} items, {elapsed:.1f} s)",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_report(items, preds, info), encoding="utf-8")
    log.info("wrote %s (%d items, %.1f s)", args.out, len(preds), elapsed)
    predictions = args.predictions
    if predictions is None and args.subset == "all":
        predictions = args.golden_dir / "predictions.jsonl"
    if predictions is not None:
        predictions.write_text("".join(p.model_dump_json() + "\n" for p in preds), encoding="utf-8")
        log.info("wrote %s", predictions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
