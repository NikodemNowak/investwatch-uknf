from __future__ import annotations

from sqlalchemy import func, select

from investwatch.collectors.seeds import load_seed_sources
from investwatch.db import repo
from investwatch.db.models import FindingRow, PostRow, SourceRow
from investwatch.db.schemas import FindingFilters
from investwatch.db.session import session_scope
from investwatch.demo import replay


def test_replay_builds_everything_from_the_pipeline(db: None) -> None:
    # Eager Celery, mock AI, no network: the demo-sites crawl is covered by the full stack.
    summary = replay(sources=False, timeout_s=5)
    assert summary.pending == 0
    assert summary.posts >= 20 and summary.findings > 0
    assert set(summary.by_module) >= {"m1_third_party_ad", "m3_shadow_advisory"}
    assert summary.models == ["mock-rules-v0"]
    # The same synthetic ad on Instagram and TikTok is one finding with two occurrences.
    assert summary.duplicates >= 1
    with session_scope() as s:
        page = repo.list_findings(s, FindingFilters(q="KASIA200", page_size=10))
        assert page.total == 1 and len(page.items[0].occurrences) == 2
        # Posts of entities on the KNF warning list carry the flag.
        warned = s.scalars(select(PostRow).where(PostRow.author == "br-stone.net")).one()
        flags = s.scalars(select(FindingRow.knf_warning).where(FindingRow.post_id == warned.id))
        assert all(f and f["name"] == "Barclay Stone Ltd" for f in flags)
        # Golden labels feed calibration; nothing hand-made is in `findings`.
        assert sum(summary.calibration_labels.values()) > 50
        counted = s.scalar(select(func.count()).select_from(FindingRow))
        # The reset keeps the curated live sources (platform APIs show what they still need).
        names = set(s.scalars(select(SourceRow.name)))
    assert counted == summary.findings
    assert {spec.name for spec in load_seed_sources()} <= names

    again = replay(sources=False, timeout_s=5)  # a reset replay gives the same numbers
    assert again.by_module == summary.by_module and again.posts == summary.posts


def test_synthetic_material_is_flagged_and_real_seeds_are_compliant(db: None) -> None:
    from investwatch.collectors.policy import access_mode_of
    from investwatch.collectors.registry import COLLECTORS
    from investwatch.collectors.seeds import load_seed_sources
    from investwatch.config import get_settings
    from investwatch.demo import REAL_PREFIX, seed_real_sources, summarise_real

    summary = replay(sources=False, timeout_s=5)
    assert summary.synthetic_posts > 0
    with session_scope() as s:
        posts = list(s.scalars(select(PostRow)))
        synthetic = [p for p in posts if (p.provenance or {}).get("synthetic")]
        # Every fictional social item and fictional firm is labelled; real pages are not.
        assert any("KASIA200" in p.text for p in synthetic)
        assert not any(p.author == "br-stone.net" for p in synthetic)
        findings = repo.list_findings(s, FindingFilters(page_size=200)).items
        assert any(f.post and f.post.provenance and f.post.provenance.synthetic for f in findings)

        path = get_settings().data_dir / "seeds" / "real_demo.yaml"
        specs = load_seed_sources(path)
        assert specs and all(spec.name.startswith(REAL_PREFIX) for spec in specs)
        assert all(spec.collector in COLLECTORS for spec in specs)
        # Only official APIs and the robots-respecting crawler; never a platform page.
        assert {access_mode_of(spec.collector) for spec in specs} <= {"official_api", "crawler"}
        assert not any(
            host in spec.target
            for spec in specs
            for host in ("facebook.com", "tiktok.com", "youtube.com", "instagram.com")
        )
        assert seed_real_sources(s, path) == len(specs)
        assert seed_real_sources(s, path) == 0
        real = summarise_real(s, {"Realne: YouTube – inne": "needs_credentials"})
        assert real.posts == len(posts) - len(synthetic)
        assert real.sources["Realne: YouTube – inne"] == "needs_credentials"
