"""`make demo`: reset the database and replay the demo material through the real pipeline.

Nothing is inserted as a finished finding. The replay:

1. empties every table and runs `seed` (KNF register snapshot + fictional demo firms, demo
   sources, thresholds, golden-set calibration labels, and with `SEED_LIVE_SOURCES` the curated
   live sources, so "Monitoring" still shows the platform APIs and what each one is missing);
2. runs every enabled demo-sites source (`scrape_source`: polite fetch, Playwright render,
   analysis) - compliant / non-compliant page pairs, including one pair with the same text and
   a different layout (dedup keeps both);
3. imports files through the file-import connector (`import_file`, as `POST /api/imports`):
   a few public marketing pages of registered firms and archived pages of entities on the KNF
   warning list (both from the golden set, with provenance), and synthetic social items
   (`"synthetic": true`, fictional firms and people) in the shapes of the official APIs;
4. with `--real` (`make demo-real`): runs the real sources of `data/seeds/real_demo.yaml`
   (Microsoft Ad Library API + landing pages, KNF-registered firms' pages, live sites from the
   KNF warning list, YouTube Data API only with `YOUTUBE_API_KEY`), all live and compliant;
5. waits until every post is analysed and prints counts per module and risk level (real and
   synthetic material counted apart; `provenance.synthetic` marks the fictional items).

The model's second opinion (`llm` queue) keeps arriving afterwards and is not waited for.

Usage: `python -m investwatch.demo [--real] [--no-reset] [--timeout 900]`
(`make demo` / `make demo-real` run it in `api`).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from investwatch.collectors.imports.file_import import import_file
from investwatch.collectors.policy import collector_ready
from investwatch.collectors.seeds import load_seed_sources
from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.models import (
    Base,
    FindingRow,
    LabelRow,
    PostRow,
    ScrapeRunRow,
    SourceRow,
)
from investwatch.db.session import session_scope
from investwatch.pipeline.analyze import ingest_item
from investwatch.seed import (
    DEMO_SOURCES,
    run_migrations,
    seed_base,
    seed_golden_labels,
    seed_live_sources,
)

log = logging.getLogger(__name__)

FIRM_PAGES = (
    "https://bossa.pl/oferta/akcje-obligacje",
    "https://michaelstrom.pl/oferta/obligacje-skarbowe",
    "https://www.finax.eu/pl/produkty/inwestowanie-w-etf",
    "https://www.xtb.com/pl/ike",
)
"""Registered firms' own pages from `data/golden/public/firm_pages.jsonl` (ADR 0009).

Real firms are in the demo to show fair treatment: two pages without findings (DM BOŚ,
Michael / Ström) and two with a possible formal violation the text plainly shows (a tax
benefit without the "depends on your situation / may change" note, art. 44(2)(f) of
Regulation 2017/565), reported as medium "do weryfikacji przez analityka". Left out:
investors.pl (a TFI: the TFI register is not in our KNF snapshot, so the firm would wrongly
show as unregistered) and cmcmarkets.com (only an "ad label" point on a home page, too weak to
put a real firm on screen). Strong cases come from the fictional demo-sites."""
WARNED_PAGES = ("br-stone.net/pl/", "fximperium.com/pl/", "gcblondonltd.com/pl/")
"""Archived pages of KNF-warned entities (`data/golden/public/knf_warnings_wayback.jsonl`)."""


@dataclass(frozen=True)
class DemoFile:
    """One file for the import connector."""

    format: str
    name: str
    content: bytes
    note: str


REAL_PREFIX = "Realne:"
"""Names of the real-data sources (`data/seeds/real_demo.yaml`)."""


class RealSummary(BaseModel):
    """What the real-data part produced (only material that is not synthetic)."""

    posts: int
    posts_by_access_mode: dict[str, int]
    posts_by_platform: dict[str, int]
    fetch_status: dict[str, int]
    """ok / blocked / error / no_text over real posts (blocked = robots.txt, 403, throttle)."""
    blocked: dict[str, str]
    """URL -> why it was not fetched (first 40)."""
    findings: int
    by_module: dict[str, dict[str, int]]
    alerts_above_threshold: int
    knf_warning_flags: int
    sources: dict[str, str]
    """Real source -> status of its last run, or why it did not run (e.g. `needs_credentials`)."""


class DemoSummary(BaseModel):
    """What the replay produced (printed as JSON by `make demo`)."""

    posts: int
    analysed: int
    duplicates: int
    findings: int
    by_module: dict[str, dict[str, int]]
    """module -> risk level -> count."""
    alerts_above_threshold: int
    knf_warning_flags: int
    sources: dict[str, str]
    """Demo source -> status of its last run."""
    calibration_labels: dict[str, int]
    models: list[str]
    llm_queued: int
    pending: int
    """Posts still waiting for analysis when the wait ended (0 = complete)."""
    seconds: float
    synthetic_posts: int = 0
    real: RealSummary | None = None


def reset_database(session: Session) -> None:
    """Delete every row (the schema stays; Alembic's version table is not in the metadata)."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())


def _jsonl(rows: list[dict[str, object]]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def _golden_rows(path: Path, wanted: tuple[str, ...]) -> list[dict[str, object]]:
    """Rows of a golden public file, one per wanted URL, in `wanted` order."""
    by_url: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            by_url.setdefault(str(row["url"]), row)
    return [by_url[u] for u in wanted if u in by_url and by_url[u].get("text")]


def demo_files(data_dir: Path) -> list[DemoFile]:
    """The files the replay imports, with the provenance note the analyst would enter."""
    golden = data_dir / "golden" / "public"
    firms = [
        {
            "external_id": r["url"],
            "url": r["url"],
            "platform": "web",
            "author": r["author"],
            "text": r["text"],
            "lang": "pl",
        }
        for r in _golden_rows(golden / "firm_pages.jsonl", FIRM_PAGES)
    ]
    warned = []
    for r in _golden_rows(golden / "knf_warnings_wayback.jsonl", WARNED_PAGES):
        prov = r["provenance"]
        assert isinstance(prov, dict)
        warned.append(
            {
                "external_id": str(r["ref"]),
                "url": prov["source_url"],
                "platform": "web",
                "author": r["author"],
                "text": r["text"],
                "lang": "pl",
            }
        )
    synthetic = data_dir / "fixtures" / "synthetic"
    files = [
        DemoFile(
            "posts_jsonl",
            "firm_pages.jsonl",
            _jsonl(firms),
            "Strony marketingowe firm z rejestru KNF (zbiór wzorcowy, pobrane 2026-11-21 "
            "zgodnie z robots.txt)",
        ),
        DemoFile(
            "posts_jsonl",
            "knf_warnings_wayback.jsonl",
            _jsonl(warned),
            "Archiwalne strony podmiotów z listy ostrzeżeń publicznych KNF (Internet Archive, "
            "zbiór wzorcowy)",
        ),
        DemoFile(
            "posts_jsonl",
            "social.jsonl",
            (data_dir / "demo" / "social.jsonl").read_bytes(),
            "DANE SYNTETYCZNE: fikcyjne wpisy demo (M1, M3)",
        ),
    ]
    for name, fmt in (
        ("meta_ads.json", "meta_ads_json"),
        ("tiktok_ccl.json", "tiktok_ccl_json"),
        ("youtube_api.json", "youtube_api_json"),
    ):
        files.append(
            DemoFile(fmt, name, (synthetic / name).read_bytes(), "DANE SYNTETYCZNE: fikcyjne")
        )
    return files


def import_demo_files(files: list[DemoFile]) -> list[str]:
    """Import files like `POST /api/imports` does and queue their analysis; returns post ids."""
    from investwatch.jobs.tasks import analyze_post

    queued: list[str] = []
    for f in files:
        items = import_file(
            f.format, f.content, filename=f.name, imported_by="demo", provenance_note=f.note
        )
        batch: list[str] = []
        with session_scope() as session:
            for item in items:
                result = ingest_item(session, item)
                if result.changed and result.post.fetch_status == "ok":
                    batch.append(str(result.post.id))
        log.info("imported %s: %d items, %d to analyse", f.name, len(items), len(batch))
        for post_id in batch:
            analyze_post.delay(post_id)
        queued += batch
    return queued


def run_demo_sources() -> list[uuid.UUID]:
    """Queue every enabled demo-sites source (the same task Beat schedules)."""
    from investwatch.jobs.tasks import scrape_source

    names = {str(s["name"]) for s in DEMO_SOURCES if s["collector"] == "web" and s["enabled"]}
    with session_scope() as session:
        ids = list(
            session.scalars(
                select(SourceRow.id).where(SourceRow.name.in_(names), SourceRow.enabled.is_(True))
            )
        )
    for source_id in ids:
        scrape_source.delay(str(source_id))
    return ids


def seed_real_sources(session: Session, path: Path) -> int:
    """Create the real-data sources not present yet; returns how many were added."""
    existing = set(session.scalars(select(SourceRow.name)))
    added = 0
    for spec in load_seed_sources(path):
        if not spec.name.startswith(REAL_PREFIX):
            raise ValueError(f"real source names must start with {REAL_PREFIX!r}: {spec.name}")
        if spec.name not in existing:
            # The replay queues the run itself; Beat takes over from the next cron slot.
            from investwatch.jobs.tasks import next_run

            repo.create_source(
                session, **spec.model_dump(), next_run_at=next_run(spec.cron, datetime.now(UTC))
            )
            added += 1
    return added


def run_real_sources() -> tuple[list[uuid.UUID], dict[str, str]]:
    """Queue every real source whose connector is ready; the others are reported, not run."""
    from investwatch.jobs.tasks import scrape_source

    settings = get_settings()
    queued: list[uuid.UUID] = []
    skipped: dict[str, str] = {}
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(SourceRow).where(
                    SourceRow.name.like(f"{REAL_PREFIX}%"), SourceRow.enabled.is_(True)
                )
            )
        )
        for row in rows:
            blocked = collector_ready(row.collector, settings)
            if blocked is None:
                queued.append(row.id)
            else:
                skipped[row.name] = blocked.status
    for source_id in queued:
        scrape_source.delay(str(source_id))
    return queued, skipped


def _pending(session: Session, source_ids: list[uuid.UUID]) -> tuple[int, int]:
    """(sources without a finished run, posts not analysed yet)."""
    finished = set(
        session.scalars(
            select(ScrapeRunRow.source_id).where(
                ScrapeRunRow.source_id.in_(source_ids), ScrapeRunRow.finished_at.is_not(None)
            )
        )
    )
    rows = session.execute(
        select(PostRow.trace).where(
            PostRow.fetch_status == "ok", PostRow.text != "", PostRow.duplicate_of.is_(None)
        )
    ).all()
    return len(set(source_ids) - finished), sum(1 for (trace,) in rows if not trace)


def wait_for_pipeline(source_ids: list[uuid.UUID], timeout_s: float, poll_s: float = 2.0) -> int:
    """Poll until every demo source ran and every post was analysed; returns posts pending."""
    deadline = time.monotonic() + timeout_s
    pending_posts = 0
    while True:
        with session_scope() as session:
            pending_sources, pending_posts = _pending(session, source_ids)
        if not pending_sources and not pending_posts:
            return 0
        if time.monotonic() >= deadline:
            log.warning(
                "timed out: %d sources and %d posts still pending", pending_sources, pending_posts
            )
            return pending_posts
        log.info("waiting: %d sources, %d posts", pending_sources, pending_posts)
        time.sleep(poll_s)


def _synthetic(post: PostRow) -> bool:
    return bool((post.provenance or {}).get("synthetic"))


def summarise_real(session: Session, skipped: dict[str, str]) -> RealSummary:
    """Counts over real (not synthetic) posts and their findings."""
    thresholds = repo.get_thresholds(session)
    posts = [p for p in session.scalars(select(PostRow)) if not _synthetic(p)]
    real_ids = {p.id for p in posts}
    modes: Counter[str] = Counter()
    platforms: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    blocked: dict[str, str] = {}
    for p in posts:
        modes[str((p.provenance or {}).get("access_mode") or "?")] += 1
        platforms[p.platform] += 1
        statuses[p.fetch_status] += 1
        if p.fetch_status in {"blocked", "error"} and len(blocked) < 40:
            blocked[p.url] = (p.provenance or {}).get("fetch_error") or p.fetch_status
    by_module: dict[str, dict[str, int]] = {}
    alerts = warnings = 0
    for f in session.scalars(select(FindingRow).where(FindingRow.post_id.in_(real_ids))):
        risks = by_module.setdefault(f.module, {"high": 0, "medium": 0, "low": 0})
        risks[f.risk_level] = risks.get(f.risk_level, 0) + 1
        alerts += int(f.score >= thresholds.for_module(f.module))  # type: ignore[arg-type]
        warnings += int(bool(f.knf_warning))
    sources = {
        s.name: s.last_status or "never"
        for s in session.scalars(select(SourceRow).where(SourceRow.name.like(f"{REAL_PREFIX}%")))
    }
    sources.update(skipped)
    return RealSummary(
        posts=len(posts),
        posts_by_access_mode=dict(modes.most_common()),
        posts_by_platform=dict(platforms.most_common()),
        fetch_status=dict(statuses.most_common()),
        blocked=blocked,
        findings=sum(sum(r.values()) for r in by_module.values()),
        by_module=dict(sorted(by_module.items())),
        alerts_above_threshold=alerts,
        knf_warning_flags=warnings,
        sources=dict(sorted(sources.items())),
    )


def summarise(session: Session, pending: int, seconds: float) -> DemoSummary:
    """Counts the screens will show."""
    thresholds = repo.get_thresholds(session)
    by_module: dict[str, dict[str, int]] = {}
    alerts = warnings = queued = 0
    models: Counter[str] = Counter()
    for f in session.scalars(select(FindingRow)):
        risks = by_module.setdefault(f.module, {"high": 0, "medium": 0, "low": 0})
        risks[f.risk_level] = risks.get(f.risk_level, 0) + 1
        alerts += int(f.score >= thresholds.for_module(f.module))  # type: ignore[arg-type]
        warnings += int(bool(f.knf_warning))
        queued += int(f.llm_review == "queued")
        models[f.model] += 1
    sources = {
        s.name: s.last_status or "never"
        for s in session.scalars(select(SourceRow).where(SourceRow.name.like("Demo:%")))
    }
    labels = {
        str(module): int(n)
        for module, n in session.execute(
            select(LabelRow.module, func.count()).group_by(LabelRow.module)
        )
    }

    def count(*where: ColumnElement[bool]) -> int:
        return session.scalar(select(func.count()).select_from(PostRow).where(*where)) or 0

    return DemoSummary(
        posts=count(),
        analysed=count(PostRow.trace.is_not(None), PostRow.duplicate_of.is_(None)),
        duplicates=count(PostRow.duplicate_of.is_not(None)),
        findings=sum(sum(r.values()) for r in by_module.values()),
        by_module=dict(sorted(by_module.items())),
        alerts_above_threshold=alerts,
        knf_warning_flags=warnings,
        sources=dict(sorted(sources.items())),
        calibration_labels=dict(sorted(labels.items())),
        models=sorted(models),
        llm_queued=queued,
        pending=pending,
        seconds=round(seconds, 1),
        synthetic_posts=sum(1 for p in session.scalars(select(PostRow)) if _synthetic(p)),
    )


def replay(
    *, reset: bool = True, sources: bool = True, real: bool = False, timeout_s: float = 900.0
) -> DemoSummary:
    """Reset (optionally), seed and replay the demo (+ the real sources); returns the summary."""
    t0 = time.monotonic()
    data_dir = get_settings().data_dir
    run_migrations()
    with session_scope() as session:
        if reset:
            reset_database(session)
        seed_base(session)
        seed_golden_labels(session)
        if get_settings().seed_live_sources:
            seed_live_sources(session)
        if real:
            seed_real_sources(session, data_dir / "seeds" / "real_demo.yaml")
    source_ids = run_demo_sources() if sources else []
    skipped: dict[str, str] = {}
    if real:
        real_ids, skipped = run_real_sources()
        source_ids += real_ids
    import_demo_files(demo_files(data_dir))
    pending = wait_for_pipeline(source_ids, timeout_s)
    with session_scope() as session:
        summary = summarise(session, pending, time.monotonic() - t0)
        if real:
            summary.real = summarise_real(session, skipped)
        return summary


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-reset", action="store_true", help="keep existing data")
    parser.add_argument("--no-sources", action="store_true", help="skip the demo-sites crawl")
    parser.add_argument(
        "--real", action="store_true", help="also run the real sources (real_demo.yaml)"
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="seconds to wait")
    args = parser.parse_args()
    logging.basicConfig(level=get_settings().log_level, format="%(levelname)s %(message)s")
    summary = replay(
        reset=not args.no_reset,
        sources=not args.no_sources,
        real=args.real,
        timeout_s=args.timeout,
    )
    print(summary.model_dump_json(indent=2))
    if summary.pending:
        raise SystemExit("demo replay incomplete: some posts were not analysed in time")


if __name__ == "__main__":
    main()
