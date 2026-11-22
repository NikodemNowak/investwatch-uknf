from __future__ import annotations

import pytest

from investwatch_ai.rules import M2_RULE_IDS, RuleContext, evaluate, load_rules
from investwatch_ai.schemas import Post, RegisteredFirm, RuleResult


def _results(text: str, firm: RegisteredFirm | None = None) -> dict[str, RuleResult]:
    return {r.rule_id: r for r in evaluate(RuleContext.build(text, firm=firm))}


def _status(text: str, rule_id: str, firm: RegisteredFirm | None = None) -> str:
    return _results(text, firm)[rule_id].status


def test_yaml_has_all_18_rules_with_metadata() -> None:
    rules = load_rules()
    assert set(M2_RULE_IDS) == {str(i) for i in range(1, 19) if i != 12} | {"12a", "12b"}
    assert set(rules) >= set(M2_RULE_IDS)
    for rid in M2_RULE_IDS:
        meta = rules[rid]
        assert meta.name and meta.legal_basis.startswith("art.")
        assert meta.type in {"text", "render", "llm"}
        assert 0 < meta.weight <= 1
    assert rules["3"].weight == 0.9
    assert rules["18"].weight == 0.9
    assert rules["9"].weight == 0.3


def test_evaluate_returns_every_m2_rule_in_order() -> None:
    results = evaluate(RuleContext.build("Zwykły tekst bez treści inwestycyjnych."))
    assert [r.rule_id for r in results] == list(M2_RULE_IDS)
    for r in results:
        assert r.legal_basis == load_rules()[r.rule_id].legal_basis


def test_render_rules_unknown_without_snapshot() -> None:
    res = _results("Zarabiaj do 25% miesięcznie. Inwestowanie wiąże się z ryzykiem.")
    for rid in ("4", "5", "6", "7", "8"):
        assert res[rid].status == "unknown"
        assert res[rid].check_type == "render"


# Rule 1: firm identification
def test_rule1_pass_with_inflected_official_name(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Mazowiecki Bank Inwestycyjny S.A."]
    assert _status(posts["05"].text, "1", firm) == "pass"


def test_rule1_fail_with_trade_name_only(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Nordvik Markets ApS Spółka Akcyjna Oddział w Polsce"]
    r = _results(posts["06"].text, firm)["1"]
    assert r.status == "fail"


def test_rule1_without_firm_uses_legal_form() -> None:
    assert _status("Dom Maklerski Złoty Róg S.A. zaprasza.", "1") == "pass"
    assert _status("Nordvik – zarabiaj na ropie!", "1") == "fail"


# Rule 2: ad label
def test_rule2(posts: dict[str, Post]) -> None:
    assert _status(posts["02"].text, "2") == "pass"  # "#reklama"
    assert _status(posts["04"].text, "2") == "pass"  # "Materiał marketingowy"
    assert _status(posts["06"].text, "2") == "pass"  # "Sponsorowane"
    assert _status(posts["03"].text, "2") == "fail"  # promo landing, no label
    assert _status(posts["01"].text, "2") == "fail"  # affiliate link, no label
    assert _status("Dziś pada deszcz.", "2") == "na"


# Rule 3: gains without risk
def test_rule3_gains_without_risk_fails() -> None:
    r = _results("Gwarantujemy 100% zysku w rok! Dołącz teraz.")["3"]
    assert r.status == "fail"
    assert r.evidence and r.evidence[0].quote
    assert "100% zysku" in r.evidence[0].quote


def test_rule3_fixture_posts(posts: dict[str, Post]) -> None:
    assert _status(posts["01"].text, "3") == "fail"  # 340% / minimum 100%, no warning
    # 05 speaks of gains only in tax sentences ("Zyski na IKE są zwolnione z podatku"): rule 16.
    assert _status(posts["05"].text, "3") == "na"
    assert _status(posts["06"].text, "3") == "pass"  # warning present (in English: rule 10)
    assert _status("Nowa siedziba biura w Gdańsku.", "3") == "na"


def test_rule3_cfd_loss_statistic_is_not_a_gain(posts: dict[str, Post]) -> None:
    assert _status(posts["02"].text, "3") == "na"


# Rule 10: language consistency
def test_rule10_english_warning_in_polish_ad(posts: dict[str, Post]) -> None:
    assert _status(posts["06"].text, "10") == "fail"
    assert _status(posts["05"].text, "10") == "pass"
    assert _status("Promocja na kawę.", "10") == "na"


# Rule 14: past performance disclaimer
def test_rule14(posts: dict[str, Post]) -> None:
    assert _status(posts["04"].text, "14") == "fail"  # +68% w 3 lata, no disclaimer
    assert _status(posts["08"].text, "14") == "fail"  # 17 trafionych sygnałów z 20
    ok = (
        "Fundusz Alfa: +12% za lata 2021–2025. Wyniki historyczne nie stanowią "
        "wiarygodnego wskaźnika przyszłych wyników."
    )
    assert _status(ok, "14") == "pass"
    assert _status(posts["05"].text, "14") == "na"


# Rule 15: forecasts
def test_rule15(posts: dict[str, Post]) -> None:
    r = _results(posts["03"].text)["15"]
    assert r.status == "fail"  # "Zarabiaj do 25% miesięcznie"
    assert _status(posts["01"].text, "15") == "fail"  # "w tym roku spokojnie zrobicie minimum 100%"
    ok = (
        "Prognozujemy stopę zwrotu 8% w 2027 r. Prognoza nie jest wiarygodnym "
        "wskaźnikiem przyszłych wyników."
    )
    assert _status(ok, "15") == "pass"
    assert _status(posts["02"].text, "15") == "na"


# Rule 16: tax
def test_rule16(posts: dict[str, Post]) -> None:
    assert _status(posts["05"].text, "16") == "pass"
    assert _status("Inwestuj bez podatku Belki na IKE!", "16") == "fail"
    assert _status(posts["02"].text, "16") == "na"


# Rules 17 and 18: supervisor
def test_rules_17_18_fail_on_knf_approval_and_safety(posts: dict[str, Post]) -> None:
    res = _results(posts["04"].text)
    assert res["17"].status == "fail"
    assert res["18"].status == "fail"
    assert res["18"].evidence[0].quote is not None
    assert "bezpieczne" in res["18"].evidence[0].quote


def test_rule18_short_phrase() -> None:
    res = _results("Jesteśmy nadzorowani przez KNF – Twoje pieniądze są bezpieczne.")
    assert res["18"].status == "fail"


def test_rules_17_18_informational_mention_passes() -> None:
    res = _results(
        "Dom Maklerski Złoty Róg S.A. podlega nadzorowi Komisji Nadzoru Finansowego. "
        "Inwestowanie wiąże się z ryzykiem."
    )
    assert res["17"].status == "pass"
    assert res["18"].status == "pass"


def test_rules_17_18_na_without_supervisor(posts: dict[str, Post]) -> None:
    res = _results(posts["02"].text)
    assert res["17"].status == "na"
    assert res["18"].status == "na"


@pytest.mark.parametrize("rid", ["9", "11", "13"])
def test_llm_and_render_history_rules_are_unknown_when_applicable(rid: str, posts) -> None:  # type: ignore[no-untyped-def]
    assert _status(posts["04"].text, rid) == "unknown"


def test_rule12a_fails_on_three_year_history(posts: dict[str, Post]) -> None:
    # "Wynik za lata 2023-2025": three years, no "since inception" note.
    assert _status(posts["04"].text, "12a") == "fail"


def test_history_rules_na_without_past_performance(posts: dict[str, Post]) -> None:
    res = _results(posts["05"].text)
    for rid in ("12a", "12b", "13"):
        assert res[rid].status == "na"


# ------------------------------------------------ boilerplate on real firm pages (quality round)


def test_rule3_tax_rate_sentence_is_not_a_gain_claim() -> None:
    text = (
        "Rachunek maklerski do handlu akcjami i obligacjami.\n"
        "Podatek od zysków giełdowych rozliczany jest rocznie według jednej stawki - 19%.\n"
        "Zaloguj się do serwisu, aby złożyć zlecenie."
    )
    assert _status(text, "3") == "na"


def test_rule15_calculator_label_without_a_figure_is_not_a_forecast() -> None:
    text = (
        "Jednorazowa wpłata\nzł\nOkres inwestowania\nlat\nSuma wpłat\n0 zł\n"
        "Spodziewany wynik z Finax info\n0 zł\nInwestowanie wiąże się z ryzykiem."
    )
    assert _status(text, "15") == "na"
    assert _status("Spodziewany zysk w tym roku to 12% rocznie, bez ryzyka.", "15") == "fail"


def test_art76_elements_ignore_the_cookie_banner() -> None:
    from investwatch_ai.rules import M3_ELEMENT_IDS

    text = (
        "Konto IKE: inwestuj w akcje i ETF bez podatku od zysków kapitałowych.\n"
        "Używamy plików cookies, żeby strona działała prawidłowo, była wygodna w obsłudze i lepiej"
        " dopasowana do Twoich potrzeb.\n"
    )
    res = {r.rule_id: r for r in evaluate(RuleContext.build(text), M3_ELEMENT_IDS)}
    assert res["76a"].status == "pass"


def _firm(name: str) -> RegisteredFirm:
    import uuid

    return RegisteredFirm(
        id=uuid.uuid4(),
        name=name,
        aliases=[],
        domains=[],
        handles=[],
        kind="dom_maklerski",
        country="PL",
        services=["A1"],
        register_url="https://www.knf.gov.pl/",
    )


def test_rule1_legal_form_written_out_passes() -> None:
    firm = _firm("DOM MAKLERSKI BANKU OCHRONY ŚRODOWISKA S.A.")
    text = "Dom Maklerski Banku Ochrony Środowiska Spółka Akcyjna z siedzibą w Warszawie."
    assert _status(text, "1", firm) == "pass"
    firm = _firm("Przykład Inwestycje sp. z o.o.")
    text = "Przykład Inwestycje spółka z ograniczoną odpowiedzialnością, ul. Prosta 1."
    assert _status(text, "1", firm) == "pass"


def test_rule15_interest_on_cash_is_a_rate_not_a_forecast() -> None:
    text = (
        "Oprocentowanie wolnych środków\n"
        "Nawet do 3.50% w skali roku przez pierwsze 90 dni od założenia konta."
    )
    assert _status(text, "15") == "na"


def test_art76e_polish_word_mam_is_not_a_mam_account() -> None:
    from investwatch_ai.rules import M3_ELEMENT_IDS

    def status(text: str) -> str:
        res = {r.rule_id: r for r in evaluate(RuleContext.build(text), M3_ELEMENT_IDS)}
        return res["76e"].status

    assert (
        status("Zaznaczając to pole, akceptuję regulamin i potwierdzam, że mam 18 lat.") == "pass"
    )
    assert status("Otwórz konto PAMM lub MAM, a nasi traderzy pomnożą Twój kapitał.") == "fail"


def test_past_performance_needs_a_result_not_the_verb_to_work_out() -> None:
    text = "Zanim zaczniesz handlować na giełdzie, warto poćwiczyć i wypracować strategie."
    assert _status(text, "14") == "na" and _status(text, "12b") == "na"


def test_rule2_ignores_privacy_notice_and_sponsorship_news() -> None:
    text = (
        "Obligacje skarbowe w ofercie domu maklerskiego, z opisem ryzyka stopy procentowej.\n"
        "Administratorem Pani/Pana danych osobowych jest Przykład DM S.A. Kliknij aby dowiedzieć"
        " się jakie przysługują ci prawa w związku z przetwarzaniem Twoich danych osobowych.\n"
        "Z dumą dołączamy do tej historii jako Główny Partner Klubu."
    )
    assert _status(text, "2") == "na"


def test_rule2_quotes_the_offer_rather_than_the_first_weak_cue() -> None:
    text = (
        "Z dumą dołączamy do tej historii jako Główny Partner Klubu. Dołącz do nas!\n"
        "0% prowizji na wszystkie CFD na akcje notowane na giełdach w Polsce.\n"
    )
    r = _results(text)["2"]
    assert r.status == "fail" and "0% prowizji" in (r.evidence[0].quote or "")


def test_repeated_cues_are_quoted_once() -> None:
    from investwatch_ai.rules import M3_ELEMENT_IDS

    text = "Kupuj ETFs teraz. Polecamy ETFs. Najlepsze ETFs na rynku. Inwestuj w ETFs."
    r = {x.rule_id: x for x in evaluate(RuleContext.build(text), M3_ELEMENT_IDS)}["76b"]
    assert r.explanation.count("„ETFs”") == 1


def test_short_history_counts_consecutive_years_in_words() -> None:
    text = (
        "Materiał marketingowy. Wyniki historyczne funduszu: 2014: 5%, 2016: 7%, 2017: 3%,"
        " 2018: 4%. Wyniki historyczne nie gwarantują przyszłych wyników.\n"
    )
    r = _results(text)["12a"]
    assert r.status == "fail"
    assert "najwyżej 3 kolejne lata (2014, 2016, 2017, 2018)" in r.explanation
