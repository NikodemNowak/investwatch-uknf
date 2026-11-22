"""One-shot bootstrap: migrations, the KNF register, demo sources and calibration labels.

Idempotent. It never inserts posts or findings: every finding on the screens comes from the
pipeline (`make demo` replays the demo material through it, see `investwatch.demo`).

Usage: `python -m investwatch.seed` (the `seed` Compose service).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from investwatch.collectors.seeds import load_seed_sources
from investwatch.config import get_settings
from investwatch.db import repo
from investwatch.db.models import SettingRow, SourceRow
from investwatch.db.session import session_scope
from investwatch.golden.build import load_items
from investwatch.registry import sync as registry_sync

log = logging.getLogger(__name__)

DEMO_HOST = "http://demo-sites"
DEMO_PAGES: list[tuple[str, str, bool]] = [
    # (file, source name, enabled). Pairs of compliant / non-compliant pages (index.html).
    ("ok.html", "Demo: strona zgodna (ok.html)", True),
    ("ok-maly-druk.html", "Demo: ten sam tekst, ostrzeżenie 9 px (ok-maly-druk.html)", True),
    ("compliant.html", "Demo: wzorcowa reklama (compliant.html)", True),
    ("no-risk.html", "Demo: zyski bez ostrzeżenia (no-risk.html)", True),
    ("tiny-font.html", "Demo: ostrzeżenie 10 px (tiny-font.html)", True),
    ("low-contrast.html", "Demo: niski kontrast (low-contrast.html)", True),
    ("occluded-risk.html", "Demo: ostrzeżenie zasłonięte (occluded-risk.html)", True),
    ("footer-risk.html", "Demo: ostrzeżenie w stopce (footer-risk.html)", True),
    ("collapsed-risk.html", "Demo: ostrzeżenie zwinięte (collapsed-risk.html)", True),
    ("mobile-clipped.html", "Demo: ucięte na telefonie (mobile-clipped.html)", True),
    ("past-performance.html", "Demo: wynik bez zastrzeżeń (past-performance.html)", True),
    ("past-performance-ok.html", "Demo: wyniki z zastrzeżeniami (past-performance-ok.html)", True),
    ("promo-zloto.html", "Demo: PrimeFX24, promocja złota (promo-zloto.html)", True),
    ("tdm-zastrzezone.html", "Demo: zastrzeżenie TDM (tdm-zastrzezone.html)", True),
    ("zablokowana-robots.html", "Demo: zamknięta w robots.txt (zablokowana-robots.html)", True),
    # Disabled so the live "check URL" demo is the first time this page is analysed.
    ("hidden-risk.html", "Demo: ukryte ryzyko (hidden-risk.html)", False),
]

DEMO_SOURCES: list[dict[str, object]] = [
    *(
        {
            "name": name,
            "collector": "web",
            "target": f"{DEMO_HOST}/{file}",
            "module_hint": "m2_risk_disclosure",
            "cron": "0 */6 * * *",
            "enabled": enabled,
        }
        for file, name, enabled in DEMO_PAGES
    ),
    {
        "name": "Próbki UKNF (fixtures)",
        "collector": "sample",
        "target": "",
        "module_hint": None,
        "cron": "0 3 * * *",
        "enabled": False,
    },
]


def run_migrations() -> None:
    """Upgrade the database to the latest revision."""
    config = Config()
    config.set_main_option("script_location", "investwatch.db:migrations")
    command.upgrade(config, "head")


def seed_base(session: Session) -> dict[str, int]:
    """KNF register (snapshot + fictional demo firms), demo sources and thresholds."""
    existing = set(session.scalars(select(SourceRow.name)))
    sources = 0
    for spec in DEMO_SOURCES:
        if spec["name"] not in existing:
            repo.create_source(session, **spec)
            sources += 1
    if session.get(SettingRow, repo.THRESHOLDS_KEY) is None:
        repo.set_thresholds(session, repo.get_thresholds(session))
    # Offline: the committed register snapshot + demo firms; Beat refreshes it live daily.
    register = registry_sync.sync(session, live=False)
    return {
        "register_firms": register.total,
        "demo_firms": register.extra_firms,
        "sources_added": sources,
    }


def golden_labels(golden_dir: Path) -> list[dict[str, Any]]:
    """Golden items as `labels` rows, with the scores of the last `make eval`.

    Only compliant sources (no scraped social items) and items not excluded by a reviewer;
    items without a prediction are skipped.
    """
    predictions_path = golden_dir / "predictions.jsonl"
    if not predictions_path.exists():
        return []
    scores = {}
    for line in predictions_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            pred = json.loads(line)
            scores[pred["item_id"]] = float(pred["score"])
    rows = []
    for item in load_items(golden_dir / "golden.jsonl"):
        if item.excluded or not item.provenance.headline or item.id not in scores:
            continue
        rows.append(
            {
                "ref": item.id,
                "post_id": None,
                "module": item.module,
                "label": item.label,
                "rule_labels": dict(item.rule_labels),
                "score": scores[item.id],
                "split": item.split,
                "origin": item.origin,
                "provenance": item.provenance.model_dump(),
                "labeler": item.review.by if item.review else item.labeler,
            }
        )
    return rows


def seed_golden_labels(session: Session) -> int:
    """Load the golden set into `labels` (`source=golden`); replaces earlier golden rows."""
    rows = golden_labels(get_settings().data_dir / "golden")
    if not rows:
        log.info("no golden predictions: run `make eval` to seed calibration labels")
        return 0
    return repo.replace_golden_labels(session, rows)


def seed_live_sources(session: Session) -> int:
    """Add the curated live sources (`data/seeds/sources.yaml`) not present yet."""
    existing = set(session.scalars(select(SourceRow.name)))
    added = 0
    for spec in load_seed_sources():
        if spec.name not in existing:
            repo.create_source(session, **spec.model_dump())
            added += 1
    return added


def main() -> None:
    """Migrate and seed."""
    logging.basicConfig(level=get_settings().log_level)
    run_migrations()
    with session_scope() as session:
        counts = seed_base(session)
        counts["golden_labels"] = seed_golden_labels(session)
        if get_settings().seed_live_sources:
            counts["live_sources_added"] = seed_live_sources(session)
    log.info("seed done: %s", counts)


if __name__ == "__main__":
    main()
