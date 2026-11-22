"""Public-data loaders (`golden/sources/`): offline, on fixtures, no network."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from investwatch.golden.sources import curate, firm_pages, knf_warnings, records, wayback
from investwatch.golden.sources.http import USER_AGENT, PoliteClient, RobotsDisallowedError

FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC = Path(__file__).resolve().parents[3] / "data" / "golden" / "public"


def test_knf_warning_list_parses_sections_domains_and_drops_individuals() -> None:
    total, entities = knf_warnings.parse((FIXTURES / "knf_warnings.html").read_text("utf-8"))
    assert total == 7
    assert len(entities) == 5  # two private individuals dropped (data minimisation)
    by_name = {e.name.split()[0]: e for e in entities}
    assert by_name["Aurum"].section == "banking" and not by_name["Aurum"].advisory
    cbs = by_name["CBS"]
    assert cbs.section == "investment_services"
    assert cbs.art69_points == [2, 4, 5] and cbs.domains == ["cbsmarket.co"]
    assert cbs.advisory
    assert by_name["Copernicus"].advisory and by_name["Copernicus"].domains == []


def test_knf_helpers() -> None:
    assert knf_warnings.domains_in("platforma www.Example-Trade.com oraz sp.z o.o") == [
        "example-trade.com"
    ]
    assert knf_warnings.art69_points("art. 69 ust. 2 pkt 1, 2 i 5 ustawy") == [1, 2, 5]
    assert knf_warnings.section_of("z art. 178 ustawy o obrocie (...)") == "investment_services"
    assert not knf_warnings.is_legal_person("Jan Kowalski", "-", [])


def test_wayback_capture_choice() -> None:
    assert wayback.pick_capture([]) is None
    stamps = ["20200101000000", "20190101000000", "20210101000000"]
    assert wayback.pick_capture(stamps) == "20200101000000"
    assert wayback.paths_tried("x.com") == ["x.com/", "x.com/pl/"]


def test_offer_links_stay_on_site_and_skip_logins() -> None:
    html = (
        '<a href="/pl/promocje">Promocja</a><a href="https://other.pl/ike">IKE</a>'
        '<a href="/login">Konto</a><a href="/pl/kariera">Praca</a><a href="/pl/ike">IKE IKZE</a>'
    )
    links = firm_pages.offer_links(html, "https://firm.pl/pl/", 5)
    assert links == ["https://firm.pl/pl/ike", "https://firm.pl/pl/promocje"]


def test_excerpt_keeps_rule_sentences_and_redacts_contacts() -> None:
    filler = "Lorem ipsum dolor sit amet. " * 400
    text = (
        "Oferta IKE. Napisz: jan@firma.pl, tel. 22 123 45 67. "
        + filler
        + "Ulga zależy od indywidualnej sytuacji klienta. "
        + filler
        + "Firma S.A., KRS 0000123456."
    )
    out = curate.excerpt(text)
    assert len(out) < len(text) / 2
    assert "indywidualnej sytuacji" in out
    assert "KRS 0000123456" in out  # identifiers are not phone numbers
    assert "jan@firma.pl" not in out and "22 123 45 67" not in out


def _candidate(ref: str) -> dict[str, object]:
    return {
        "ref": ref,
        "domain": "scam.example",
        "entity": "Scam Ltd",
        "section": "investment_services",
        "art69_points": [5],
        "original_url": "scam.example/",
        "archive_url": "https://web.archive.org/web/2020/scam.example/",
        "timestamp": "20200101000000",
        "retrieved_at": "2026-11-21",
        "lang": "pl",
        "text": "Nasi doradcy powiedzą Ci, co kupić. " * 20,
    }


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_curate_joins_labels_skips_exclusions_and_keeps_committed(tmp_path: Path) -> None:
    root = tmp_path / "golden"
    pub = root / records.PUBLIC_DIR
    _jsonl(pub / "_candidates" / "wayback.jsonl", [_candidate("a"), _candidate("b")])
    base = {"module": "m3_shadow_advisory", "labeler": "rule", "confidence": 0.8}
    _jsonl(
        pub / "labels" / "knf_warnings_wayback.jsonl",
        [{**base, "ref": "a", "label": 1}, {**base, "ref": "b", "label": None}],
    )
    recs = curate.curate(root, "knf_warnings_wayback")
    assert [r.ref for r in recs] == ["a"]
    rec = recs[0]
    assert rec.provenance.method == "web_archive" and rec.provenance.compliant == "yes"
    assert rec.provenance.source == "knf_warnings_wayback"
    assert rec.provenance.source_url and rec.provenance.licence
    assert rec.group.startswith("entity:scam-ltd")
    records.save_records(pub / "knf_warnings_wayback.jsonl", recs)

    # Fresh checkout: candidates are git-ignored, the committed record is kept.
    (pub / "_candidates" / "wayback.jsonl").unlink()
    again = curate.curate(root, "knf_warnings_wayback")
    assert [r.ref for r in again] == ["a"]

    items = records.public_items(root)
    assert len(items) == 1
    item = items[0]
    assert item.origin == "real" and item.label == 1 and item.labeler == "rule"
    assert item.provenance.headline
    assert item.id.startswith("pub-m3-knf_warnings_wayback-")


def test_polite_client_honours_robots_and_identifies_itself() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: InvestWatchBot\nDisallow: /private\n")
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})

    client = PoliteClient(min_interval_s=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    assert client.get("https://site.example/public").text == "ok"
    with pytest.raises(RobotsDisallowedError):
        client.get("https://site.example/private/page")
    assert all(r.headers["user-agent"] == USER_AGENT for r in seen)
    assert [r.url.path for r in seen] == ["/robots.txt", "/public"]


def test_committed_public_records_are_valid_and_provenanced() -> None:
    files = sorted(PUBLIC.glob("*.jsonl"))
    assert files, "curated public sources missing"
    for path in files:
        for rec in records.load_records(path):
            prov = rec.provenance
            assert prov.compliant == "yes" and prov.headline
            assert prov.source == path.stem
            assert prov.source_url and prov.retrieved_at and prov.licence
            assert "@" not in rec.text or "[email]" in rec.text
