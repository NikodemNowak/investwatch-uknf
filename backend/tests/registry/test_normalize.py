from __future__ import annotations

import pytest

from investwatch.registry.normalize import (
    domains_in_text,
    fold,
    handle_key,
    host_path,
    is_distinctive,
    legal_form_of,
    registrable_domain,
    strip_legal_form,
)


@pytest.mark.parametrize(
    ("name", "core", "form"),
    [
        ("XTB S.A.", "xtb", "S.A."),
        ("DOM MAKLERSKI AFS Sp. z o.o.", "dom maklerski afs", "Sp. z o.o."),
        ("Kyrenia Prime Ltd", "kyrenia prime", "Ltd"),
        ("IG Europe GmbH", "ig europe", "GmbH"),
        ("Etoro (Europe) Ltd", "etoro", "Ltd"),
        ("CMC Markets Germany GmbH sp. z o.o. Oddział w Polsce", "cmc markets germany", None),
        ("Admiral Markets AS", "admiral markets", "AS"),
    ],
)
def test_strip_legal_form(name: str, core: str, form: str | None) -> None:
    assert strip_legal_form(name) == core
    if form is not None:
        assert legal_form_of(name) == form


def test_fold_removes_diacritics_and_case() -> None:
    assert fold("ŁÓDŹ Złoty Róg ŚLĄSKI") == "lodz zloty rog slaski"


def test_generic_names_are_not_distinctive() -> None:
    assert not is_distinctive(["bank"])
    assert not is_distinctive(["capital", "invest", "markets"])
    assert not is_distinctive(["inwestycje", "polska"])
    assert is_distinctive(["wisla", "capital"])


def test_registrable_domain() -> None:
    assert registrable_domain("https://www.XTB.com/pl/promo") == "xtb.com"
    assert registrable_domain("pekao.com.pl") == "pekao.com.pl"
    assert registrable_domain("http://demo-sites/promo-zloto.html") == "demo-sites"
    assert registrable_domain("zlotyrog.example") == "zlotyrog.example"
    assert registrable_domain("ul.pu") == ""
    assert registrable_domain("http://[broken") == ""


def test_domains_in_text_skips_emails_and_addresses() -> None:
    text = "Wejdź na https://www.xtb.com/pl/ lub bossa.pl; kontakt@firma.pl, ul.Puławska 1, S.A."
    assert [d for d, _ in domains_in_text(text)] == ["xtb.com", "bossa.pl"]


def test_handles_and_paths() -> None:
    assert handle_key("@XTB_Polska") == "xtbpolska"
    assert handle_key("Nordvik Markets") == "nordvikmarkets"
    assert host_path("http://www.demo-sites/promo-zloto.html?x=1") == "demo-sites/promo-zloto.html"
