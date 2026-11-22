"""Demo-sites part of the golden set: our own test pages of fictional firms (`demo-sites/`).

Each page was built to break (or satisfy) specific rules, documented in
`demo-sites/public/index.html`; only those rules are labelled, the rest are not scored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from investwatch.collectors.html_text import html_to_text
from investwatch.core.schemas import Post
from investwatch.golden.schemas import GoldenItem, GoldenPost, Provenance
from investwatch.golden.synth import parse_rules
from investwatch.pipeline.dedup import content_hash
from investwatch.registry.match import match_firms, register_status

DEMO = Provenance(collector="demo_sites", method="demo_site", compliant="yes")
HOST = "http://demo-sites"


@dataclass(frozen=True)
class DemoPage:
    """One page of `demo-sites/public/` with its intended verdict."""

    file: str
    label: int
    rules: str
    note: str


PAGES: list[DemoPage] = [
    DemoPage("compliant.html", 0, "3=pass 4=pass 5=pass 6=pass 7=pass 8=pass", "model ad"),
    DemoPage("ok.html", 0, "3=pass", "fund ad with a balanced risk warning"),
    DemoPage("no-risk.html", 1, "3=fail", "gains without a risk warning"),
    DemoPage("tiny-font.html", 1, "4=fail", "risk warning 10 px vs 16 px body"),
    DemoPage("low-contrast.html", 1, "5=fail", "pale grey risk warning on white"),
    DemoPage("occluded-risk.html", 1, "5=fail", "promo sticker covers the risk warning"),
    DemoPage("footer-risk.html", 1, "6=fail", "risk warning only in the footer"),
    DemoPage("collapsed-risk.html", 1, "7=fail", "risk warning behind a click"),
    DemoPage("mobile-clipped.html", 1, "8=fail", "risk warning clipped on phones"),
    DemoPage("past-performance.html", 1, "13=fail 14=fail", "dominant result, no disclaimer"),
    DemoPage(
        "past-performance-ok.html",
        0,
        "12a=pass 12b=pass 13=pass 14=pass",
        "past results with all disclaimers",
    ),
    DemoPage("promo-zloto.html", 1, "4=fail 8=fail", "9 px footer, collapsed on phones"),
    DemoPage("hidden-risk.html", 1, "4=fail 5=fail 6=fail 7=fail", "collapsed, 9 px, pale"),
]


def demo_root(repo: Path) -> Path:
    """`demo-sites/public/` of this checkout."""
    return repo / "demo-sites" / "public"


def item_id(page: DemoPage) -> str:
    """Stable golden id of a demo page."""
    return f"demo-m2-{page.file.removesuffix('.html')}"


def _post(url: str, text: str) -> Post:
    now = datetime.now(UTC)
    return Post(
        id=uuid.uuid4(),
        platform="web",
        collector="web",
        external_id=url,
        url=url,
        canonical_url=url,
        author="demo-sites",
        author_url=HOST,
        text=text,
        lang="pl",
        content_hash=content_hash(text),
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=None,
        first_seen_at=now,
        last_seen_at=now,
    )


def demo_items(repo: Path) -> list[GoldenItem]:
    """Golden items for the demo pages (render snapshots in `synthetic/render/`)."""
    from investwatch.golden.real import registry_firms

    firms = list(registry_firms())
    items: list[GoldenItem] = []
    for page in PAGES:
        url = f"{HOST}/{page.file}"
        text = html_to_text((demo_root(repo) / page.file).read_text(encoding="utf-8"))
        matches = match_firms(_post(url, text), firms)
        rules = parse_rules(page.rules)
        items.append(
            GoldenItem(
                id=item_id(page),
                module="m2_risk_disclosure",
                label=1 if page.label else 0,
                rule_labels=rules,
                origin="synthetic",
                provenance=DEMO,
                group="domain:demo-sites",
                post=GoldenPost(
                    platform="web",
                    collector="demo_sites",
                    external_id=url,
                    url=url,
                    author="demo-sites",
                    author_url=HOST,
                    text=text,
                ),
                html_path=f"../../demo-sites/public/{page.file}",
                render_path=f"synthetic/render/{item_id(page)}.json",
                firm_matches=matches[:5],
                register_status=register_status(matches),
                labeler="generator",
                confidence=0.9,
                note=f"demo-sites: {page.note} (labels: only the rules the page targets)",
            )
        )
    return items
