"""One regression test per root cause found in the train-split error analysis.

Each case paraphrases a train item (never a hold-out item) that the rules got wrong in
`rules-v1`; the item id is in the test name or comment. See docs/eval/latest.md.
"""

from __future__ import annotations

import pytest

from investwatch_ai.rules import M3_ELEMENT_IDS, RuleContext, evaluate
from investwatch_ai.schemas import RuleResult


def _res(text: str, ids: tuple[str, ...] | None = None) -> dict[str, RuleResult]:
    ctx = RuleContext.build(text)
    return {r.rule_id: r for r in (evaluate(ctx, ids) if ids else evaluate(ctx))}


def _st(text: str, rid: str) -> str:
    ids = M3_ELEMENT_IDS if rid.startswith("76") else None
    return _res(text, ids)[rid].status


# Rule 15: forecasts were detected too broadly (coupons, contract terms, bare "prognoza").
def test_rule15_coupon_rate_is_not_a_forecast() -> None:  # syn-m2-015, syn-m2-031
    text = "Obligacje korporacyjne z kuponem do 9% w skali roku. Kupuj bez prowizji."
    assert _st(text, "15") == "na"


def test_rule15_contract_terms_are_not_a_forecast() -> None:
    text = "Regulamin przewiduje opłatę 0,2% za przechowywanie instrumentów."
    assert _st(text, "15") == "na"


def test_rule15_weak_word_without_figure_is_not_a_forecast() -> None:
    assert _st("Przeczytaj nasze prognozy makro na blogu.", "15") == "na"


def test_rule15_weak_word_with_return_figure_is_a_forecast() -> None:
    assert _st("Nasza prognoza: fundusz zarobi w tym roku 14%.", "15") == "fail"


def test_rule15_explicit_forecast_still_fails() -> None:
    assert _st("Zarobisz nawet 25% rocznie na tej strategii!", "15") == "fail"


def test_rule15_disclaimer_alone_is_not_a_forecast() -> None:
    text = "Prognozy nie są wiarygodnym wskaźnikiem przyszłych wyników."
    assert _st(text, "15") == "na"


# Rule 10: an English warning was not recognised as a risk warning at all.
def test_rule10_english_risk_warning_detected() -> None:  # syn-m2-013, syn-m2-032
    text = (
        "Handluj CFD na złocie i indeksach z dźwignią. Zarabiaj na wzrostach i spadkach. "
        "Investing involves risk. You may lose part or all of your capital."
    )
    res = _res(text)
    assert res["3"].status == "pass"
    assert res["10"].status == "fail"


# Rules 12a / 12b: the period check was LLM-only; fee wording was too narrow.
def test_rule12a_single_year_fails() -> None:  # syn-m2-022
    text = (
        "Wyniki historyczne: stopa zwrotu za rok 2025: +18,0%. Wynik za rok 2025. "
        "Wyniki uwzględniają opłaty i prowizje."
    )
    res = _res(text)
    assert res["12a"].status == "fail"
    assert res["12b"].status == "pass"


def test_rule12a_five_years_pass() -> None:  # syn-m2-004
    text = (
        "Wyniki historyczne. Stopa zwrotu: 2021 +12,4%, 2022 -9,8%, 2023 +15,1%, 2024 +6,3%, "
        "2025 +18,0%. Stopy zwrotu w pełnych latach kalendarzowych 2021-2025."
    )
    assert _st(text, "12a") == "pass"


def test_rule12a_short_history_since_inception_is_not_failed() -> None:
    text = "Wyniki historyczne od początku działalności funduszu: 2024 +5%, 2025 +7%."
    assert _st(text, "12a") != "fail"


def test_rule12a_month_result_fails() -> None:  # syn-m1-002 style
    assert _st("Mój portfel osiągnął w październiku +14%!", "12a") == "fail"


# Rule 16: a bare "IKE" in a menu is not a tax claim.
def test_rule16_menu_product_name_is_not_a_tax_claim() -> None:
    assert _st("Oferta / Rachunek maklerski / Rachunek IKE / IKZE / Kontakt", "16") == "na"


def test_rule16_tax_benefit_without_disclaimer_fails() -> None:  # syn-m2-014
    text = "Zyski z IKE po 60. roku życia są zwolnione z 19% podatku od zysków kapitałowych."
    assert _st(text, "16") == "fail"


# Rule 18: "your data is safe" next to a KNF note is not an investment-safety claim.
def test_rule18_data_security_next_to_knf_passes() -> None:  # syn-m2-034
    text = (
        "Logowanie chroni uwierzytelnianie dwuskładnikowe. Twoje dane są bezpieczne i "
        "szyfrowane. Firma podlega nadzorowi Komisji Nadzoru Finansowego."
    )
    assert _st(text, "18") == "pass"


def test_rule18_supervision_as_safety_argument_still_fails() -> None:
    text = "Jesteśmy nadzorowani przez KNF, więc Twoje pieniądze są u nas bezpieczne."
    assert _st(text, "18") == "fail"


# Rule 3 / M1 markers: fee waivers are promotion, not gains; sponsor segments are labelled.
def test_rule3_fee_waiver_is_not_a_gains_claim() -> None:  # syn-m1-001
    text = "Z mojego linku w bio dostaniesz 3 miesiące bez prowizji! #współpraca"
    res = _res(text)
    assert res["3"].status == "na"
    assert res["2"].status == "pass"


def test_rule2_sponsor_segment_counts_as_label() -> None:  # syn-m1-018
    text = "Sponsorem odcinka jest Pilica Inwestycje: obligacje z kuponem 9% rocznie."
    assert _st(text, "2") == "pass"


def test_rule3_high_risk_wording_counts_as_warning() -> None:
    text = "Potencjalnie wysoki zwrot z inwestycji w zamian za podwyższone ryzyko dla inwestorów."
    assert _st(text, "3") == "pass"


# Art. 76 elements: personalisation and buy/sell calls were missed.
@pytest.mark.parametrize(
    ("text", "rid"),
    [
        # syn-m3-005
        ("Podaję listę 5 spółek do kupienia, dobraną do Twojego budżetu.", "76a"),
        ("Podaję listę 5 spółek do kupienia, dobraną do Twojego budżetu.", "76c"),
        ("Kupuj, gdy dam sygnał, sprzedawaj, gdy napiszę.", "76c"),
        # syn-m3-006
        ("Wypełnij ankietę profilu ryzyka i otrzymasz spersonalizowaną rekomendację.", "76a"),
        ("Napiszemy, które ETF-y i obligacje skarbowe kupić za Twoje oszczędności.", "76c"),
        # syn-m3-008, syn-m3-015
        ("Rekomendujemy konkretne fundusze oraz obligacje dopasowane do Twoich potrzeb.", "76c"),
        ("Dobiorę Ci gotowy portfel ETF: konkretne 3 fundusze i proporcje.", "76c"),
        # syn-m3-004
        ("Daj mi dostęp do swojego rachunku, a ja będę zarządzać Twoim portfelem.", "76e"),
    ],
)
def test_advisory_elements_detected(text: str, rid: str) -> None:
    assert _st(text, rid) == "fail"


def test_advisory_negated_recommendation_is_not_an_element() -> None:
    text = "Materiał nie stanowi rekomendacji zakupu ani sprzedaży instrumentów finansowych."
    assert _st(text, "76c") == "pass"


# Second pass: synthetic TRAIN items (data/golden/synthetic/haiku_v1.jsonl, generator:haiku),
# only where the generator and the blind verifier agree on the rule verdict.
def test_rule15_analyst_forecast_with_hedged_disclaimer_passes() -> None:  # haiku m2neg-03
    text = (
        "Scenariusz bazowy to wzrost 4-5% rocznie. To jest prognoza analityczna, a nie "
        "obietnica zysku. Rzeczywiste wyniki mogą być istotnie niższe lub ujemne."
    )
    assert _st(text, "15") == "pass"


def test_rule15_past_result_this_year_is_not_a_forecast() -> None:  # haiku hardpos-13
    assert _st("Fundusz w tym roku zyskał 12,5%. Zapraszamy do zapisów.", "15") == "na"


def test_rule15_future_gain_this_year_is_still_a_forecast() -> None:
    assert _st("W tym roku zarobisz na tym funduszu 12%.", "15") == "fail"


def test_rule18_negated_safety_is_not_a_safety_claim() -> None:  # haiku m2neg-26, m2neg-30
    text = (
        "Czy inwestycja jest bezpieczna? Każda inwestycja niesie ryzyko straty, a nadzór KNF "
        "nie chroni przed spadkami. Fundusz nie ma gwarancji zwrotu. Firma działa pod nadzorem KNF."
    )
    assert _st(text, "18") == "pass"


def test_rule18_sleep_well_under_supervision_fails() -> None:  # haiku hardpos-24
    text = "Jesteśmy pod nadzorem KNF, więc możesz spać spokojnie. Nie stracisz pieniędzy."
    assert _st(text, "18") == "fail"


def test_rule17_regulator_checked_our_product_fails() -> None:  # haiku hardpos-11
    text = (
        "Nasz fundusz uzyskał zgodę KNF. Regulator sprawdził nasz produkt i go zatwierdził, "
        "to gwarancja jakości."
    )
    assert _st(text, "17") == "fail"


def test_rule12a_month_year_range_counts_all_years() -> None:  # haiku m2neg-01
    text = (
        "Wyniki w ostatnich 5 latach (01.2021–12.2025): +38,4% w PLN, po opłatach. "
        "Wyniki przeszłe nie są gwarancją przyszłych zysków."
    )
    assert _st(text, "12a") == "pass"


# Third pass: real licensed-firm pages (PR #19, train split): navigation, buttons and footers
# carried the promotional cues that fired rules 2, 3 and 15.
NAV_PAGE = (
    "Giełda\nForex\nOtwórz konto\nDołącz\nZyski\nLogowanie\n"
    "Oferta giełdowa obejmuje akcje i ETF-y na GPW oraz rynkach zagranicznych.\n"
    "Prowizje od zleceń są opisane w tabeli opłat dostępnej w dokumentach rachunku.\n"
    "© 2025 Dom Maklerski Przykład S.A. Wszelkie prawa zastrzeżone.\n"
)


def test_navigation_buttons_do_not_make_a_page_an_unlabelled_ad() -> None:  # firm_pages-4e3f…
    assert _st(NAV_PAGE, "2") != "fail"


def test_navigation_word_zyski_is_not_a_gains_claim() -> None:  # firm_pages-725c…
    assert _st(NAV_PAGE, "3") != "fail"


def test_hashtag_ad_label_on_its_own_line_still_counts() -> None:
    text = "Załóż konto przez mój link i zgarnij bonus 200 zł na start!\n#reklama #współpraca"
    assert _st(text, "2") == "pass"


def test_promo_sentence_in_body_still_needs_a_label() -> None:
    text = (
        "Giełda\nOtwórz konto\nZarabiaj nawet 20% rocznie, dołącz do nas już dziś i otwórz konto!"
    )
    assert _st(text, "2") == "fail"


# Fourth pass: archived pages of entities on the KNF warning list (PR #19, train split).
@pytest.mark.parametrize(
    "text",
    [
        "Gold account: personal account manager and daily market analysis.",  # wayback-cac7…
        "Osobisty menedżer konta pomoże Ci w każdej transakcji.",  # wayback-7301…
        "Dedykowany opiekun konta przygotuje strategię dla Ciebie.",
        "Doradztwo indywidualne klienta przez naszych analityków.",  # wayback-f1c8…
    ],
)
def test_m3_personal_manager_cues_are_personalised_advice(text: str) -> None:
    assert _st(text, "76a") == "fail"


@pytest.mark.parametrize(
    "text",
    [
        "Codzienne sygnały transakcyjne prosto na Twój telefon.",  # wayback-4a18…
        "Receive daily trading signals from our analysts.",
        "Kompleksowe doradztwo analityków przy każdej transakcji.",  # wayback-cfd1…
    ],
)
def test_m3_trading_signal_cues_are_buy_sell_recommendations(text: str) -> None:
    assert _st(text, "76c") == "fail"


@pytest.mark.parametrize(
    "text",
    [
        "Serwis PAMM: inwestuj z najlepszymi traderami.",  # wayback-ae9f…
        "Managed accounts for clients who have no time to trade.",
        "Konto zarządzane przez naszych ekspertów.",
        "Our automated trading system trades your money 24/7.",  # wayback-f5e9…
    ],
)
def test_m3_managed_account_cues_are_portfolio_management(text: str) -> None:
    assert _st(text, "76e") == "fail"


def test_rare_gain_words_in_a_long_product_page_are_not_an_unlabelled_ad() -> None:
    # firm_pages-725c…, -4e3f…, -2ea4…: product descriptions mention "zysk" once or twice.
    filler = "Rachunek maklerski pozwala kupować akcje i obligacje notowane na giełdzie. " * 12
    text = filler + "Zyski z inwestycji rozlicza się w zeznaniu rocznym PIT-38."
    assert _st(text, "2") != "fail"


def test_gain_heavy_short_post_still_needs_a_label() -> None:
    text = "Zyski 30% w miesiąc! Moje zyski rosną. Zarabiaj jak ja."
    assert _st(text, "2") == "fail"


def test_bare_gain_word_on_a_long_page_is_not_a_gain_claim() -> None:  # firm_pages-725c…
    filler = "Rachunek maklerski pozwala kupować akcje i obligacje notowane na giełdzie. " * 12
    assert _st(filler + "Zyski z inwestycji rozlicza się w zeznaniu rocznym.", "3") == "na"


def test_gain_with_figure_on_a_long_page_still_needs_risk() -> None:
    filler = "Rachunek maklerski pozwala kupować akcje i obligacje notowane na giełdzie. " * 12
    assert _st(filler + "Nasi klienci zyskali średnio 14% rocznie.", "3") == "fail"


@pytest.mark.parametrize(
    "text",
    [
        "Pozycja krótka – otwierasz ją, gdy spodziewasz się spadku ceny akcji.",  # 7e98…
        "Jeśli stopy rosną lub tego spodziewają się inwestorzy, ceny obligacji spadają.",  # 646d…
        "Fundusze dopasowane do wybranych poziomów ryzyka, oczekiwanej stopy zwrotu i horyzontu.",
        "Otwierasz pozycję w zależności od przewidywanego kierunku zmian ceny.",
    ],
)
def test_rule15_investor_expectation_in_education_is_not_a_forecast(text: str) -> None:
    assert _st(text, "15") == "na"
