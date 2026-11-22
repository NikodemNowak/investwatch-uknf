"""Join a source's candidates with its labels into the committed `public/<source>.jsonl`.

Usage (from `backend/`):
    uv run python -m investwatch.golden.sources.curate knf_warnings_wayback
    uv run python -m investwatch.golden.sources.curate firm_pages
    uv run python -m investwatch.golden.sources.curate --list knf_warnings_wayback  # unlabelled

Candidates (git-ignored, `public/_candidates/`) are what the loaders downloaded; labels
(`public/labels/<source>.jsonl`, committed) are the labeller's decisions. Only labelled,
non-excluded candidates reach the golden set. Texts are cut to an `excerpt` (enough for
the rules, no full-page copies) with e-mail addresses and phone numbers removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

from investwatch.golden.schemas import Provenance
from investwatch.golden.sources import firm_pages, wayback
from investwatch.golden.sources.records import (
    PUBLIC_DIR,
    PublicRecord,
    SourceLabel,
    domain_group,
    save_records,
)

log = logging.getLogger(__name__)

HEAD_CHARS = 3000
TAIL_CHARS = 2000
KEY_CHARS = 4500
"""Excerpt budget: the first `HEAD_CHARS` (the offer), the sentences in between that carry
what the rules look at (`KEY_SENTENCE`, up to `KEY_CHARS`) and the last `TAIL_CHARS` (the
footer: firm identification and risk warnings). Never a full-page copy."""
KEY_SENTENCE = re.compile(
    r"ryzyk|strat|utrat|przeszło|przyszł|wynik|stop[aęy] zwrotu|rentown|zysk|gwarant|prognoz|"
    r"podat|sytuacj|KNF|Komisj\w* Nadzoru|nadzor|zezwoleni|licencj|regulowan|reklam|"
    r"doradztw|doradc|rekomendac|zarządza\w* portfel|sygnał|risk|lose|past performance|tax|"
    r"regulated|advice|\d+(?:[.,]\d+)?\s?%",
    re.I,
)
BOILERPLATE = re.compile(r"Czas ekspiracji|ciasteczk|cookie", re.I)
ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(
    r"\+\d{1,3}[\s-]?\(?\d{1,4}\)?(?:[\s-]?\d{2,4}){2,4}"
    r"|(?:\btel\.?|telefon\w*|phone|call us)[:\s]*[\d ()+-]{9,}\d",
    re.I,
)


def redact(text: str) -> str:
    """Drop e-mail addresses and phone numbers (data minimisation; the rules need neither)."""
    text = ZERO_WIDTH.sub("", text)
    return PHONE.sub("[tel]", EMAIL.sub("[email]", text))


def excerpt(text: str) -> str:
    """Head, rule-relevant middle sentences and tail of a page text, redacted."""
    text = redact(text)
    if len(text) <= HEAD_CHARS + KEY_CHARS + TAIL_CHARS:
        return text
    middle = text[HEAD_CHARS:-TAIL_CHARS]
    keep: list[str] = []
    used = 0
    for sentence in re.split(r"(?<=[.!?])\s+", middle):
        if BOILERPLATE.search(sentence) or not KEY_SENTENCE.search(sentence):
            continue
        sentence = sentence.strip()[:600]
        if used + len(sentence) > KEY_CHARS:
            break
        keep.append(sentence)
        used += len(sentence) + 1
    body = "\n".join(keep)
    return f"{text[:HEAD_CHARS]}\n[...]\n{body}\n[...]\n{text[-TAIL_CHARS:]}"


def _entity_group(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:40].strip("-")
    return f"entity:{slug}-{hashlib.sha256(name.encode()).hexdigest()[:6]}"


def wayback_record(cand: dict[str, object], lab: SourceLabel) -> PublicRecord:
    """Archived page of a KNF-warned entity."""
    c = wayback.Candidate.model_validate(cand)
    return PublicRecord(
        ref=c.ref,
        module=lab.module,
        label=int(lab.label or 0),
        rule_labels=lab.rule_labels,
        labeler=lab.labeler,
        confidence=lab.confidence,
        note=lab.note,
        group=lab.group or _entity_group(c.entity),
        url=c.original_url,
        author=c.domain,
        lang=c.lang,
        text=excerpt(c.text),
        provenance=Provenance(
            collector="wayback",
            method="web_archive",
            compliant="yes",
            source="knf_warnings_wayback",
            source_url=c.archive_url,
            retrieved_at=c.retrieved_at,
            licence=wayback.LICENCE,
        ),
    )


def firm_record(cand: dict[str, object], lab: SourceLabel) -> PublicRecord:
    """Page from a KNF-registered firm's own website."""
    c = firm_pages.FirmPage.model_validate(cand)
    return PublicRecord(
        ref=c.ref,
        module=lab.module,
        label=int(lab.label or 0),
        rule_labels=lab.rule_labels,
        labeler=lab.labeler,
        confidence=lab.confidence,
        note=lab.note,
        group=lab.group or domain_group(c.url),
        url=c.url,
        author=c.firm,
        lang=c.lang,
        text=excerpt(c.text),
        provenance=Provenance(
            collector="web",
            method="http_robots_respecting",
            compliant="yes",
            source="firm_pages",
            source_url=c.url,
            retrieved_at=c.retrieved_at,
            licence=firm_pages.LICENCE,
        ),
    )


SOURCES: dict[str, tuple[str, Callable[[dict[str, object], SourceLabel], PublicRecord]]] = {
    "knf_warnings_wayback": ("wayback.jsonl", wayback_record),
    "firm_pages": ("firm_pages.jsonl", firm_record),
}
"""Source id -> (candidates file, record builder)."""


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def curate(root: Path, source: str) -> list[PublicRecord]:
    """Labelled, non-excluded candidates of `source` as records.

    A label whose candidate is missing keeps the record already committed (the candidates
    are git-ignored, so a fresh checkout can re-curate without re-downloading).
    """
    cand_file, builder = SOURCES[source]
    cands = {str(c["ref"]): c for c in _jsonl(root / PUBLIC_DIR / "_candidates" / cand_file)}
    rows = _jsonl(root / PUBLIC_DIR / f"{source}.jsonl")
    committed = {f"{r['ref']}|{r['module']}": r for r in rows}
    out: list[PublicRecord] = []
    for row in _jsonl(root / PUBLIC_DIR / "labels" / f"{source}.jsonl"):
        lab = SourceLabel.model_validate(row)
        if lab.label is None:
            continue
        cand = cands.get(lab.ref)
        if cand is not None:
            out.append(builder(cand, lab))
        elif (old := committed.get(f"{lab.ref}|{lab.module}")) is not None:
            rec = PublicRecord.model_validate(old)
            out.append(
                rec.model_copy(
                    update={
                        "label": int(lab.label),
                        "rule_labels": lab.rule_labels,
                        "labeler": lab.labeler,
                        "confidence": lab.confidence,
                        "note": lab.note,
                        "group": lab.group or rec.group,
                    }
                )
            )
        else:
            log.warning("%s: label for %s has no candidate; re-run the loader", source, lab.ref)
    return out


def unlabelled(root: Path, source: str) -> list[dict[str, object]]:
    """Candidates without a label yet."""
    cand_file, _ = SOURCES[source]
    done = {str(r["ref"]) for r in _jsonl(root / PUBLIC_DIR / "labels" / f"{source}.jsonl")}
    return [
        c
        for c in _jsonl(root / PUBLIC_DIR / "_candidates" / cand_file)
        if str(c["ref"]) not in done
    ]


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--list", action="store_true", help="print unlabelled candidate refs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    root = Path(__file__).resolve().parents[5] / "data" / "golden"
    if args.list:
        for cand in unlabelled(root, args.source):
            print(cand["ref"])
        return
    recs = curate(root, args.source)
    save_records(root / PUBLIC_DIR / f"{args.source}.jsonl", recs)
    log.info("%s: %d records", args.source, len(recs))


if __name__ == "__main__":
    main()
