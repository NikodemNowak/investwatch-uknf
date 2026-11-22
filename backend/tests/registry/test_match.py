from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import pytest

from investwatch.config import get_settings
from investwatch.core.schemas import FirmMatch, Platform, Post
from investwatch.registry.knf import load_snapshot
from investwatch.registry.match import FirmIndex, match_post, register_status
from investwatch.registry.sync import apply_brands, load_extra_firms, snapshot_path

DEMO = Path(__file__).resolve().parents[3] / "demo-sites" / "public"


@cache
def _index() -> FirmIndex:
    settings = get_settings()
    records = apply_brands(
        load_snapshot(snapshot_path(settings)).records, settings.registry_dir / "brands.json"
    )
    return FirmIndex(
        [r.to_firm() for r in records] + load_extra_firms(settings.registry_extra_paths)
    )


def _post(
    text: str,
    url: str = "https://www.youtube.com/watch?v=abc",
    author: str = "@KasiaInwestuje",
    platform: Platform = "youtube",
    author_url: str | None = None,
) -> Post:
    now = datetime.now(UTC)
    return Post(
        id=uuid.uuid4(),
        platform=platform,
        collector="test",
        external_id=url,
        url=url,
        canonical_url=url,
        author=author,
        author_url=author_url,
        text=text,
        lang="pl",
        content_hash="x",
        html_key=None,
        render_key=None,
        screenshot_keys={},
        published_at=None,
        first_seen_at=now,
        last_seen_at=now,
    )


def _web(url: str, text: str) -> Post:
    host = url.split("/")[2]
    return _post(text, url=url, author=host, platform="web", author_url=f"http://{host}")


def _match(post: Post) -> list[FirmMatch]:
    return match_post(post, _index())


def _names(matches: list[FirmMatch], on: str | None = None) -> set[str]:
    return {m.firm.name for m in matches if on is None or m.on == on}


def test_exact_name_with_legal_form() -> None:
    matches = _match(_post("XTB S.A. zaprasza na webinar o rynku akcji."))
    top = matches[0]
    assert top.firm.name == "XTB S.A." and top.on == "content"
    assert top.method == "alias" and top.matched_text == "XTB S.A."
    assert top.confidence >= 0.9


def test_registered_domain_makes_the_firm_the_author() -> None:
    matches = _match(_web("https://www.xtb.com/pl/promocja", "Otwórz konto i handluj."))
    assert matches[0].firm.name == "XTB S.A."
    assert (matches[0].on, matches[0].method, matches[0].confidence) == ("author", "domain", 1.0)
    assert register_status(matches) == "registered_without_advice"  # XTB has no A5


def test_domain_from_register_dodatkowe_informacje() -> None:
    matches = _match(_web("https://www.ausprime.eu/pl", "Trade with us"))
    assert matches[0].firm.name == "AC Markets (Europe) Ltd" and matches[0].on == "author"


def test_trade_name_and_former_name_aliases() -> None:
    assert "AC Markets (Europe) Ltd" in _names(_match(_post("Konto w Ausprime ma bonus")))
    assert "XTB S.A." in _names(_match(_post("Kiedyś X-Trade Brokers, dziś inna nazwa")))
    assert "mBANK S.A." in _names(_match(_post("Rachunek maklerski w mBank i eMakler")))


def test_fuzzy_typo_in_distinctive_name() -> None:
    matches = _match(_post("Polecam platformę Ausprme, konto otwarte w 5 minut"))
    fuzzy = [m for m in matches if m.method == "fuzzy"]
    assert fuzzy and fuzzy[0].firm.name == "AC Markets (Europe) Ltd"
    assert 0.5 < fuzzy[0].confidence < 0.8 and "≈" in fuzzy[0].matched_text


@pytest.mark.parametrize(
    "text",
    [
        "Bank i inwestycje to podstawa dobrego planu.",
        "Capital Invest Markets dla każdego, global trading group.",
        "Polska Grupa Inwestycyjna i dom maklerski - jak wybrać?",
        "Interaktywny kurs inwestowania, investors club, inwestorzy i inwestorki.",
        "Złoto, srebro, plus ropa: prime time dla traderów.",
        "Zobacz na IG i FB, link w bio. Kup ING? Nie, kupuję ETF.",
    ],
)
def test_generic_words_do_not_match(text: str) -> None:
    assert _match(_post(text)) == []


def test_short_acronym_needs_capitals() -> None:
    assert "XTB S.A." not in _names(_match(_post("xtb to skrót, który nic nie znaczy")))
    assert "XTB S.A." in _names(_match(_post("Konto w XTB założyłam wczoraj")))


def test_official_handle_is_author_fan_handle_is_mention() -> None:
    official = _match(
        _post("Nowa platforma", author="XTB Polska", author_url="https://youtube.com/@xtbpolska")
    )
    assert "XTB S.A." in _names(official, "author")
    fan = _match(_post("Dzisiaj o promocjach @xtb dla nowych klientów", author="@trader_bob"))
    assert "XTB S.A." in _names(fan, "content") and not _names(fan, "author")


def test_fixture_handle_and_page_name() -> None:
    matches = _match(
        _post(
            "Sponsorowane. Nordvik – zarabiaj!",
            url="https://www.facebook.com/ads/library/?id=1",
            author="Nordvik Markets",
            platform="facebook",
            author_url="https://www.facebook.com/nordvikmarkets",
        )
    )
    assert matches[0].on == "author" and matches[0].method == "handle"
    assert matches[0].firm.name.startswith("Nordvik Markets")


# ------------------------------------------------------------- router pairs (roadmap B)


def test_finfluencer_mentioning_firm_is_m1_material() -> None:
    matches = _match(_post("Konto zakładam w PrimeFX24 – z mojego linku bonus 500 zł! #współpraca"))
    assert _names(matches, "content") == {"Kyrenia Prime Ltd"}
    assert not _names(matches, "author")
    assert register_status(matches) == "not_registered"


def test_firm_page_on_unknown_domain_presents_itself_as_author() -> None:
    text = (
        "Handluj złotem bez prowizji. Otwórz konto. "
        "PrimeFX24 jest nazwą handlową Kyrenia Prime Ltd, Limassol, Cypr."
    )
    matches = _match(_web("https://zloto-promo.example/x", text))
    owner = matches[0]
    assert (owner.firm.name, owner.on, owner.method) == ("Kyrenia Prime Ltd", "author", "alias")
    assert owner.confidence == pytest.approx(0.75)
    assert "domena spoza rejestru" in owner.matched_text


def test_same_name_in_a_blog_sentence_stays_a_mention() -> None:
    text = "Kyrenia Prime Ltd reklamuje się agresywnie, ostrzegamy czytelników."
    matches = _match(_web("https://blog-o-inwestowaniu.example/wpis", text))
    assert _names(matches, "content") == {"Kyrenia Prime Ltd"} and not _names(matches, "author")


def test_warning_about_a_firm_is_not_self_presentation() -> None:
    text = "KNF ostrzega: Kyrenia Prime Ltd z siedzibą na Cyprze nie ma zezwolenia w Polsce."
    matches = _match(_web("https://portal-finansowy.example/news", text))
    assert not _names(matches, "author") and "Kyrenia Prime Ltd" in _names(matches, "content")


RANKING_PAGE = """Ranking kont maklerskich – listopad 2026
1. XTB
Konto maklerskie XTB S.A. bez prowizji do 100 000 EUR obrotu.
Dane adresowe
XTB S.A. ul. Prosta 67, 00-838 Warszawa
NIP 5270000000
Otwórz rachunek
2. Revolut
Akcje w aplikacji. Kod promocyjny KONTO10 – darmowa akcja na start.
Dane adresowe
REVOLUT LTD Oddział w Polsce, al. Jana Pawła II 43a, 31-864 Kraków
NIP 1060000000
Otwórz rachunek
3. Noble Securities
Rachunek maklerski Noble Securities z dostępem do rynków zagranicznych.
4. Alior Bank
Konto maklerskie w Alior Bank S.A. dla klientów banku.
"""


def test_ranking_page_listing_firms_is_not_a_self_presentation() -> None:
    """A third-party comparison page lists each broker's legal name next to its NIP: the
    page is about the firms, not by them (M1, never M2 for a firm it mentions; ADR 0009)."""
    url = "https://www.ranking-kont.example/ranking-kont-maklerskich"
    matches = _match(_web(url, RANKING_PAGE))
    assert not _names(matches, "author")
    assert "Revolut Securities Europe UAB" in _names(matches, "content")
    assert register_status(matches) == "not_registered"


def test_single_firm_page_on_unknown_domain_still_presents_itself() -> None:
    text = (
        "Handluj złotem bez prowizji. Konto w 5 minut. Wspieramy klientów XTB w migracji.\n"
        "PrimeFX24 jest nazwą handlową Kyrenia Prime Ltd, Limassol, Cypr."
    )
    matches = _match(_web("https://zloto-promo.example/y", text))
    assert _names(matches, "author") == {"Kyrenia Prime Ltd"}


def test_firm_page_on_its_brand_domain_naming_other_firms_stays_its_own() -> None:
    """A firm's own page (brand in the host) may name other firms, e.g. former employers."""
    text = (
        "Dołącz do nas. Nasi doradcy pracowali wcześniej w XTB, Noble Securities i Alior Bank.\n"
        "PrimeFX24 jest nazwą handlową Kyrenia Prime Ltd z siedzibą w Limassol, Cypr."
    )
    matches = _match(_web("https://www.kyreniaprime-kariera.example/dolacz", text))
    assert _names(matches, "author") == {"Kyrenia Prime Ltd"}


def test_family_office_outside_register_goes_to_m3_gate() -> None:
    text = "Kowalski Family Office – portfel szyty na miarę, powiemy co kupić."
    matches = _match(_web("https://kowalskifamilyoffice.example/oferta", text))
    assert matches == []
    assert register_status(matches) == "not_registered"


def test_demo_sites_pages_belong_to_their_fictional_firms() -> None:
    from investwatch.collectors.html_text import html_to_text

    promo = _match(
        _web(
            "http://demo-sites/promo-zloto.html",
            html_to_text((DEMO / "promo-zloto.html").read_text()),
        )
    )
    assert promo[0].firm.name == "Kyrenia Prime Ltd" and promo[0].on == "author"
    assert not _names(promo, "content") - {"Kyrenia Prime Ltd"}
    hidden = _match(
        _web(
            "http://demo-sites/hidden-risk.html",
            html_to_text((DEMO / "hidden-risk.html").read_text()),
        )
    )
    assert _names(hidden, "author") == {"Aurora Kapitał Dom Maklerski S.A."}
    assert register_status(hidden) == "registered"


def test_matching_is_fast_enough_for_the_pipeline() -> None:
    import time

    text = (DEMO / "compliant.html").read_text() * 5
    start = time.perf_counter()
    _match(_web("https://example.com/a", text))
    assert time.perf_counter() - start < 1.0


# ------------------------------------------------------------- real firms (quality round)


def _import(url: str, author: str, text: str) -> Post:
    """A web page imported from a file: the analyst entered the author's name."""
    return _post(text, url=url, author=author, platform="web")


@pytest.mark.parametrize(
    ("author", "firm"),
    [
        ("X-Trade Brokers DM S.A. (XTB)", "XTB S.A."),
        ("X-Trade Brokers Dom Maklerski S.A.", "XTB S.A."),
        ("Finax o.c.p., a.s.", "Finax"),
        ("Michael / Ström Dom Maklerski S.A.", "MICHAEL/STRÖM DOM MAKLERSKI S.A."),
        ("Dom Maklerski BOŚ S.A. (bossa.pl)", "DOM MAKLERSKI BANKU OCHRONY ŚRODOWISKA S.A."),
    ],
)
def test_author_name_former_name_or_abbreviation_is_the_author(author: str, firm: str) -> None:
    matches = _match(_import("https://archiwum.example/strona", author, "Oferta rachunku."))
    owners = _names(matches, "author")
    assert any(n.casefold().startswith(firm.casefold()) for n in owners)
    assert register_status(matches) != "not_registered"


def test_author_name_match_is_not_a_generic_word() -> None:
    matches = _match(
        _import("https://blog.example/x", "Dom Maklerski", "Jak wybrać dom maklerski?")
    )
    assert not _names(matches, "author")


@pytest.mark.parametrize("word", ["Ireland", "Germany", "Malta", "Netherlands", "London"])
def test_country_in_a_register_name_is_not_an_alias(word: str) -> None:
    text = (
        f"Fundusze ETF z siedzibą w {word}, rachunek maklerski i inwestowanie w akcje. {word} Ltd"
    )
    assert _match(_post(text)) == []


def test_eea_firm_curated_domain_is_registered_with_advice() -> None:
    matches = _match(_web("https://www.finax.eu/pl/produkty/inwestowanie-w-etf", "Portfele ETF"))
    assert matches[0].on == "author" and matches[0].firm.name.startswith("Finax")
    assert register_status(matches) == "registered"


@pytest.mark.parametrize(
    "text", ["Załóż konto handlowe i odbierz bonus.", "Nasi handlowcy oddzwonią w 5 minut."]
)
def test_trading_account_adjective_is_not_bank_handlowy(text: str) -> None:
    assert "BANK HANDLOWY S.A." not in _names(_match(_post(text)))


# ------------------------------------------------ ad-library advertisers (own ads are not M1)

ADS = Path(__file__).resolve().parents[1] / "collectors" / "fixtures" / "microsoft_ad_library"


def _bing_posts(advertiser: str) -> list[Post]:
    import json

    from investwatch.collectors.official.microsoft_ad_library import ad_item
    from investwatch.pipeline.dedup import to_post

    ads = json.loads((ADS / "search_forex.json").read_text(encoding="utf-8"))
    rows = ads.get("value", ads) if isinstance(ads, dict) else ads
    return [
        to_post(ad_item(ad, "24:forex"))
        for ad in rows
        if str(ad.get("AdvertiserName", "")).startswith(advertiser)
    ]


def test_brokers_own_bing_ad_is_by_the_firm_not_a_third_party() -> None:
    posts = _bing_posts("FxPro")
    assert posts
    for post in posts:
        matches = _match(post)
        assert _names(matches, "author") == {"FXPRO Financial Services Ltd"}
        assert "FXPRO Financial Services Ltd" not in _names(matches, "content")


def test_affiliate_bing_ad_for_a_broker_stays_a_mention() -> None:
    text = "FX Trading Platform - konto u FxPro w 5 minut. Link: simple-invest.info/Forex"
    post = _post(text, url="https://adlibrary.example/ads/1", author="Kateryna Lobotenko")
    post = post.model_copy(update={"platform": "bing"})
    matches = _match(post)
    assert not _names(matches, "author")


def test_payer_of_record_in_an_ad_library_text_is_the_author() -> None:
    text = (
        "Handluj CFD na złocie z FxPro.\nReklamodawca: FxPro Group Marketing\n"
        "Płatnik: FxPro Financial Services Ltd"
    )
    post = _post(text, url="https://www.facebook.com/ads/library/?id=9", author="FxPro Polska")
    post = post.model_copy(update={"platform": "facebook", "collector": "meta_ads_api"})
    assert _names(_match(post), "author") == {"FXPRO Financial Services Ltd"}
