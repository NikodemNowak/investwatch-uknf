from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from investwatch.registry import knf
from investwatch.registry.schemas import KnfRecord

REPO = Path(__file__).resolve().parents[3]
HTML = REPO / "data" / "fixtures" / "knf" / "html"
SNAPSHOT = REPO / "data" / "registry" / "knf_registry.json"


def _page(slug: str, page: int = 1) -> str:
    return (HTML / f"{slug}__p{page}.html").read_text(encoding="utf-8")


def _parse(kind: str, page: int = 1) -> dict[str, KnfRecord]:
    slug = knf.REGISTERS[kind]  # type: ignore[index]
    records = knf.parse_page(_page(slug, page), kind, knf.BASE_URL + slug)  # type: ignore[arg-type]
    return {r.name: r for r in records}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("dom_maklerski", 20),
        ("bank_maklerski", 10),
        ("oddzial_zagraniczny", 10),
        ("zagraniczna_bez_oddzialu", 20),
    ],
)
def test_every_register_page_parses(kind: str, expected: int) -> None:
    records = _parse(kind)
    assert len(records) == expected
    assert all(r.kind == kind and r.register_url.startswith(knf.BASE_URL) for r in records.values())


def test_xtb_with_former_name_and_mifid_services() -> None:
    xtb = _parse("dom_maklerski", page=2)["XTB S.A."]
    assert xtb.former_names == ["X-TRADE BROKERS DOM MAKLERSKI S.A."]
    assert xtb.legal_form == "S.A."
    assert xtb.country == "PL"
    # "1, 2, 3, 9, 13, 14, 16" in the KNF numbering of art. 69 UoIF.
    assert xtb.services == ["A1", "A2", "A3", "B1", "B4", "B5", "B7"]


def test_banks_keep_brokerage_office_names_and_parenthesised_aliases() -> None:
    banks = _parse("bank_maklerski")
    assert "Biuro Maklerskie mBank" in banks["mBANK S.A."].trade_names
    pko = banks["POWSZECHNA KASA OSZCZĘDNOŚCI BANK POLSKI S.A. (PKO BP S.A.)"]
    assert "PKO BP S.A." in pko.trade_names
    erste = banks["ERSTE BANK POLSKA S.A."]
    assert "SANTANDER BANK POLSKA S.A." in erste.former_names  # struck through
    # "<strike> <br />B</strike>iuro Maklerskie PEKAO": a struck letter does not strike the line.
    assert "Biuro Maklerskie PEKAO" in next(
        r.trade_names for n, r in banks.items() if n.startswith("BANK PEKAO")
    )


def test_foreign_firms_trade_names_domains_and_country() -> None:
    foreign = _parse("zagraniczna_bez_oddzialu")
    ac = foreign["AC Markets (Europe) Ltd"]
    assert "Ausprime" in ac.trade_names
    assert "AUS FOREX" in ac.former_trade_names
    assert "ausprime.eu" in ac.domains
    assert "auscapital.eu" in ac.former_domains and "auscapital.eu" not in ac.domains
    assert ac.country == "CY"
    assert "Europe" not in ac.trade_names  # generic "(Europe)" is not an alias
    kcy = foreign["50KCY LTD"]
    assert kcy.domains == ["50k.trade"]
    assert {"50COINSCY LTD", "UR Trade Fix Ltd"} <= set(kcy.former_names)
    assert all(r.supervisor for r in foreign.values())


def test_branch_has_polish_branch_name_as_alias() -> None:
    cmc = _parse("oddzial_zagraniczny")["CMC Markets Germany GmbH"]
    assert cmc.country == "DE" and cmc.services == ["A2", "A3"]
    assert any("Oddział w Polsce" in t for t in cmc.trade_names)


def test_page_count_reads_pagination() -> None:
    assert knf.page_count(_page("domy_maklerskie"), "domy_maklerskie") == 2
    slug = "notyfikowane_zagraniczne_firmy_inwestycyjne"
    assert knf.page_count(_page(slug), slug) == 36
    assert knf.page_count(_page("Banki_prowadzace_dzialalnosc_maklerska"), "x") == 1


def test_fetch_register_follows_pages_politely() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        slug = url.removeprefix(knf.BASE_URL).split("?")[0]
        page = int(url.split("page=")[1]) if "page=" in url else 1
        if not (slug == "domy_maklerskie" and page == 2):
            page = 1  # only these pages are saved; the 36 foreign pages all get page 1
        return httpx.Response(200, text=_page(slug, page))

    sleeps: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        snapshot = knf.fetch_register(client, sleep=sleeps.append)
    assert len(requested) == 2 + 1 + 1 + 36
    assert sleeps and set(sleeps) == {1.0}
    kinds = {r.kind for r in snapshot.records}
    assert kinds == set(knf.REGISTERS)
    assert any(r.name == "XTB S.A." for r in snapshot.records)
    # Repeated pages are merged, not duplicated.
    names = [(r.kind, r.name) for r in snapshot.records]
    assert len(names) == len(set(names))


def test_fetch_register_retries_then_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        knf.fetch_register(client, sleep=lambda _: None, retries=2)


def test_committed_snapshot_has_every_register(tmp_path: Path) -> None:
    snapshot = knf.load_snapshot(SNAPSHOT)
    counts = {kind: 0 for kind in knf.REGISTERS}
    for record in snapshot.records:
        counts[record.kind] += 1
    assert all(n > 0 for n in counts.values()), counts
    assert counts["zagraniczna_bez_oddzialu"] > 500
    names = {r.name for r in snapshot.records}
    assert {"XTB S.A.", "mBANK S.A."} <= names
    copy = tmp_path / "copy.json"
    knf.save_snapshot(snapshot, copy)
    assert knf.load_snapshot(copy) == snapshot


def test_firm_ids_are_stable() -> None:
    a = _parse("dom_maklerski", 2)["XTB S.A."]
    b = _parse("dom_maklerski", 2)["XTB S.A."]
    assert a.firm_id == b.firm_id
    firm = a.to_firm()
    assert firm.id == a.firm_id and "X-TRADE BROKERS DOM MAKLERSKI S.A." in firm.aliases
