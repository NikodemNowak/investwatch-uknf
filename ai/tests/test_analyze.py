from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from investwatch_ai.analyze import AnalyzeRequest, analyze
from investwatch_ai.config import Settings
from investwatch_ai.llm import OllamaClient
from investwatch_ai.schemas import Post

from .conftest import match

MOCK = Settings(ai_mode="mock")


def _req(post: Post, *matches: Any, mode: str | None = None) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(
        {"post": post.model_dump(mode="json"), "firm_matches": [m.model_dump() for m in matches]}
        | ({"mode": mode} if mode else {})
    )


def test_owner_routes_to_m2_with_all_rules(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    out = analyze(_req(posts["04"], match(firm, "author")), MOCK)
    m2 = [f for f in out.findings if f.module == "m2_risk_disclosure"]
    assert len(m2) == 1
    finding = m2[0]
    assert finding.firm == firm
    assert len(finding.rules) == 19
    assert finding.score > 0.9
    assert finding.risk_level == "high"
    assert any("bezpieczne" in q for q in finding.quotes)
    assert finding.used_llm is False
    assert out.lang == "pl"
    assert out.embedding is not None and len(out.embedding) == 1024


def test_fictional_firm_is_never_called_registered(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    """A fictional demo firm only pretends to be in the KNF register (honest demo)."""
    firm = firms["Dom Maklerski Wisła Capital S.A."].model_copy(update={"fictional": True})
    m2 = analyze(_req(posts["04"], match(firm, "author")), MOCK).findings[0]
    assert "z rejestru KNF" not in m2.explanation
    assert "Firma fikcyjna (demo) – udaje wpis w rejestrze KNF" in m2.explanation


def test_mention_only_routes_to_m1_with_rule_subset(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Kyrenia Prime Ltd"]
    out = analyze(_req(posts["01"], match(firm, "content", 0.9)), MOCK)
    m1 = next(f for f in out.findings if f.module == "m1_third_party_ad")
    assert m1.advertiser == "@InwestujZKasia"
    assert [r.rule_id for r in m1.rules] == ["2", "3", "14", "15", "17", "18"]
    assert m1.score > 0.5  # affiliate link + "z mojego linku" + promo code
    assert "Klasyfikator (leksykon)" in m1.explanation  # mock mode: no real embedding
    assert m1.model.endswith("-lexicon")


def test_ranking_page_promotes_all_named_firms(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    """A ranking page: the page owner is the advertiser, every named firm is promoted."""
    a, b = firms["Kyrenia Prime Ltd"], firms["Dom Maklerski Wisła Capital S.A."]
    out = analyze(_req(posts["01"], match(a, "content", 0.9), match(b, "content", 0.8)), MOCK)
    assert [f.module for f in out.findings if f.module != "m3_shadow_advisory"] == [
        "m1_third_party_ad"
    ]
    m1 = out.findings[0]
    assert m1.advertiser == posts["01"].author and m1.firm == a
    assert f"promuje {a.name}, {b.name}" in m1.explanation


def test_m1_signals_are_listed_once(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    """A ranking page repeats its "Advertisement" label: the explanation names it once."""
    firm = firms["Kyrenia Prime Ltd"]
    text = (
        "Ranking kont maklerskich. Advertisement. Kyrenia Prime Ltd: konto bez prowizji. "
        "Advertisement. Inny broker. ADVERTISEMENT. Załóż konto z mojego linku."
    )
    post = posts["01"].model_copy(update={"text": text})
    m1 = next(
        f
        for f in analyze(_req(post, match(firm, "content", 0.9)), MOCK).findings
        if f.module == "m1_third_party_ad"
    )
    listed = m1.explanation.split("(sygnały: ")[1].split(")")[0].split(", ")
    assert [s.lower() for s in listed].count("advertisement") == 1
    assert len({s.lower() for s in listed}) == len(listed)


def test_m1_without_classifier_is_capped_by_firm_confidence(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Kyrenia Prime Ltd"]
    plain = MOCK.model_copy(update={"classifier": False})
    out = analyze(_req(posts["01"], match(firm, "content", 0.9)), plain)
    m1 = next(f for f in out.findings if f.module == "m1_third_party_ad")
    assert 0.5 < m1.score <= 0.9
    assert "Klasyfikator" not in m1.explanation


def test_m1_fuzzy_firm_match_scales_the_head_score(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Kyrenia Prime Ltd"]
    sure = analyze(_req(posts["01"], match(firm, "content", 0.9)), MOCK)
    fuzzy = analyze(_req(posts["01"], match(firm, "content", 0.6)), MOCK)
    s1 = next(f.score for f in sure.findings if f.module == "m1_third_party_ad")
    s2 = next(f.score for f in fuzzy.findings if f.module == "m1_third_party_ad")
    assert s2 == pytest.approx(s1 * 0.6 / 0.9, abs=1e-3)


def test_unregistered_advisory_routes_to_m3(posts: dict[str, Post]) -> None:
    out = analyze(_req(posts["07"]), MOCK)
    m3 = next(f for f in out.findings if f.module == "m3_shadow_advisory")
    statuses = {r.rule_id: r.status for r in m3.rules}
    assert statuses == {"76a": "fail", "76b": "fail", "76c": "fail", "76d": "fail", "76e": "fail"}
    assert m3.risk_level == "high"
    assert m3.advertiser == posts["07"].author


def test_m3_not_triggered_for_plain_ad(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Złoty Róg S.A."]
    out = analyze(_req(posts["02"], match(firm, "content")), MOCK)
    assert {f.module for f in out.findings} == {"m1_third_party_ad"}


def test_blocked_or_empty_post_yields_no_findings(posts: dict[str, Post]) -> None:
    for key in ("09", "10"):
        out = analyze(_req(posts[key]), MOCK)
        assert out.findings == []
        assert out.lang is None


def test_mock_mode_is_deterministic(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Kyrenia Prime Ltd"]
    a = analyze(_req(posts["03"], match(firm, "author")), MOCK)
    b = analyze(_req(posts["03"], match(firm, "author")), MOCK)
    assert a.model_dump(exclude={"timings_ms"}) == b.model_dump(exclude={"timings_ms"})


def test_request_mode_overrides_settings(posts: dict[str, Post]) -> None:
    # rules mode with an unreachable Ollama: embedding degrades to None, no exception.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = OllamaClient(
        "http://x", timeout_s=1, retries=1, transport=httpx.MockTransport(handler)
    )
    out = analyze(_req(posts["04"]), Settings(ai_mode="mock"), client, mode="rules")
    assert out.embedding is None
    assert out.findings


def _llm_client(content: str | None) -> tuple[OllamaClient, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1] * 8]})
        if content is None:
            return httpx.Response(200, json={"message": {"content": "{nope"}})
        return httpx.Response(200, json={"message": {"content": content}})

    client = OllamaClient(
        "http://x",
        timeout_s=1,
        retries=3,
        backoff_s=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    return client, seen


def test_llm_mode_merges_verified_verdicts(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    reply = json.dumps(
        {
            "rules": [
                {
                    "rule_id": "11",
                    "status": "fail",
                    "confidence": 0.8,
                    "explanation": "Porównanie bez źródła.",
                    "quote": "Najlepszy wynik wśród portfeli modelowych w Polsce.",
                },
                {
                    "rule_id": "9",
                    "status": "fail",
                    "confidence": 0.9,
                    "explanation": "Zmyślony cytat.",
                    "quote": "Ten cytat nie występuje w tekście.",
                },
            ]
        },
        ensure_ascii=False,
    )
    client, seen = _llm_client(reply)
    out = analyze(_req(posts["04"], match(firm)), Settings(ai_mode="llm"), client)
    m2 = next(f for f in out.findings if f.module == "m2_risk_disclosure")
    rules = {r.rule_id: r for r in m2.rules}
    assert m2.used_llm is True
    assert rules["11"].status == "fail"
    assert rules["11"].evidence[0].quote == "Najlepszy wynik wśród portfeli modelowych w Polsce."
    assert rules["9"].status == "unknown"  # hallucinated quote is dropped
    assert out.embedding is not None
    assert sum(x * x for x in out.embedding) == pytest.approx(1.0)
    chat = next(b for b in seen if "messages" in b)
    assert "<<<" in chat["messages"][1]["content"]


def test_llm_mode_falls_back_to_rules_on_invalid_json(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    client, seen = _llm_client(None)
    out = analyze(_req(posts["04"], match(firm)), Settings(ai_mode="llm"), client)
    m2 = next(f for f in out.findings if f.module == "m2_risk_disclosure")
    assert m2.used_llm is False
    assert m2.llm_review == "unavailable"
    assert out.llm_error is not None
    assert {r.rule_id: r.status for r in m2.rules}["11"] == "unknown"
    assert sum(1 for b in seen if "messages" in b) == 3


def test_deferred_llm_marks_finding_queued_without_calling_the_model(  # type: ignore[no-untyped-def]
    posts: dict[str, Post], firms
) -> None:
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    client, seen = _llm_client(None)
    req = _req(posts["04"], match(firm)).model_copy(update={"defer_llm": True})
    out = analyze(req, Settings(ai_mode="llm"), client)
    m2 = next(f for f in out.findings if f.module == "m2_risk_disclosure")
    assert m2.llm_review == "queued"
    assert m2.used_llm is False
    assert not any("messages" in b for b in seen)
    assert out.embedding is not None
    assert out.chars > 0


def test_llm_review_reports_state_and_usage_without_embedding(  # type: ignore[no-untyped-def]
    posts: dict[str, Post], firms
) -> None:
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    client, seen = _llm_client(json.dumps({"rules": []}))
    req = _req(posts["04"], match(firm)).model_copy(update={"embed": False})
    out = analyze(req, Settings(ai_mode="llm"), client)
    m2 = next(f for f in out.findings if f.module == "m2_risk_disclosure")
    assert m2.llm_review == "done" and m2.used_llm is True
    assert out.llm is not None and out.llm.model == Settings().llm_model
    assert out.embedding is None
    assert not any(b.get("input") for b in seen)


def test_rules_mode_never_queues_a_review(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    client, _ = _llm_client(None)
    out = analyze(_req(posts["04"], match(firm), mode="rules"), Settings(), client)
    assert all(f.llm_review in ("none", "unavailable") for f in out.findings)
    assert any(f.llm_review == "unavailable" for f in out.findings)  # said, not hidden


@pytest.mark.parametrize("key", ["01", "02", "03", "04", "05", "06", "07", "08"])
def test_every_fixture_post_analyses_quickly(key: str, posts: dict[str, Post]) -> None:
    out = analyze(_req(posts[key]), MOCK)
    assert out.timings_ms["total"] < 200


def test_off_register_self_presentation_goes_to_m2_with_note(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Kyrenia Prime Ltd"]
    owner = match(firm, "author", 0.75).model_copy(
        update={"method": "alias", "matched_text": "Kyrenia Prime Ltd (domena spoza rejestru)"}
    )
    out = analyze(_req(posts["03"], owner), MOCK)
    m2 = next(f for f in out.findings if f.module == "m2_risk_disclosure")
    assert m2.firm == firm
    assert "domena spoza rejestru" in m2.explanation
    assert not any(f.module == "m1_third_party_ad" for f in out.findings)


def test_m3_gate_uses_explicit_register_status(posts: dict[str, Post], firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    base = _req(posts["07"], match(firm, "author"))
    licensed = analyze(base.model_copy(update={"register_status": "registered"}), MOCK)
    assert not any(f.module == "m3_shadow_advisory" for f in licensed.findings)
    # A firm in the KNF registers without A5 (a broker, an EEA firm) is supervised: its own
    # material is M2's business, never "doradztwo bez zezwolenia" (LABELING.md M3).
    no_a5 = analyze(base.model_copy(update={"register_status": "registered_without_advice"}), MOCK)
    assert not any(f.module == "m3_shadow_advisory" for f in no_a5.findings)
    # A mention of a registered firm does not make the publisher registered.
    mention = _req(posts["07"], match(firm, "content", 0.9))
    out = analyze(mention.model_copy(update={"register_status": "not_registered"}), MOCK)
    assert {f.module for f in out.findings} >= {"m1_third_party_ad", "m3_shadow_advisory"}


# ------------------------------------------------ registered firms (quality round, ADR 0009)


def _rules_req(text: str, firm: Any, matched_text: str = "firma.example") -> AnalyzeRequest:
    post = Post.model_validate(
        {
            "id": "00000000-0000-0000-0000-0000000000aa",
            "platform": "web",
            "collector": "test",
            "external_id": "x",
            "url": "https://firma.example/ike",
            "canonical_url": "https://firma.example/ike",
            "author": "firma.example",
            "author_url": None,
            "text": text,
            "lang": "pl",
            "content_hash": "x",
            "html_key": None,
            "render_key": None,
            "screenshot_keys": {},
            "published_at": None,
            "first_seen_at": "2026-11-21T10:00:00Z",
            "last_seen_at": "2026-11-21T10:00:00Z",
        }
    )
    owner = match(firm, "author").model_copy(
        update={"method": "domain", "matched_text": matched_text}
    )
    req = _req(post, owner)
    return req.model_copy(update={"register_status": "registered", "embed": False})


RULES = Settings(ai_mode="rules", classifier=False)
TAX_ONLY = (
    "Materiał marketingowy. Konto IKE: zyskaj zwolnienie z 19% podatku od zysków kapitałowych.\n"
    "Inwestowanie wiąże się z ryzykiem utraty części środków."
)


def test_registered_publisher_formal_omission_is_at_most_medium(firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    m2 = analyze(_rules_req(TAX_ONLY, firm), RULES).findings[0]
    assert any(r.rule_id == "16" and r.status == "fail" for r in m2.rules)
    assert m2.risk_level == "medium"
    assert "do weryfikacji przez analityka" in m2.explanation


def test_registered_publisher_with_clear_violation_stays_high(firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    text = "Materiał marketingowy. Strategia zatwierdzona przez KNF, zarabiaj 30% rocznie!"
    m2 = analyze(_rules_req(text, firm), RULES).findings[0]
    assert m2.risk_level == "high"


def test_off_register_domain_is_not_capped(firms) -> None:  # type: ignore[no-untyped-def]
    firm = firms["Dom Maklerski Wisła Capital S.A."]
    req = _rules_req(TAX_ONLY, firm, "Wisła Capital (domena spoza rejestru)")
    assert analyze(req, RULES).findings[0].risk_level == "high"


# ------------------------------------- comparison / ranking pages of licensed firms (M1, not M3)

RANKING = (
    "Ranking kont maklerskich – listopad 2026. Porównaliśmy oferty kont maklerskich dostępnych"
    " w Polsce. Oceniamy każdy rachunek pod kątem prowizji za akcje, ETF-y i kontrakty"
    " terminowe oraz bezpieczeństwa brokera (nadzór KNF).\n"
    "1. Dom Maklerski Wisła Capital S.A. – osobisty menedżer, który pomaga od pierwszego dnia."
    " Otwórz rachunek.\n"
    "2. Mazowiecki Bank Inwestycyjny S.A. – przy otwarciu wypełniasz ankietę MiFID, opieka"
    " osobistego doradcy w pakiecie premium. Otwórz rachunek.\n"
    "3. Kyrenia Prime Ltd – fundusze inwestycyjne pozwalają powierzyć zarządzanie kapitałem"
    " profesjonalistom. Kod promocyjny RANKING10. Otwórz rachunek.\n"
)


def _ranking_req(text: str, firms: Any, *names: str, confidence: float = 0.95) -> AnalyzeRequest:
    post = Post.model_validate(
        {
            "id": "00000000-0000-0000-0000-0000000000bb",
            "platform": "web",
            "collector": "test",
            "external_id": "x",
            "url": "https://ranking-kont.example/ranking-kont-maklerskich",
            "canonical_url": "https://ranking-kont.example/ranking-kont-maklerskich",
            "author": "ranking-kont.example",
            "author_url": None,
            "text": text,
            "lang": "pl",
            "content_hash": "x",
            "html_key": None,
            "render_key": None,
            "screenshot_keys": {},
            "published_at": None,
            "first_seen_at": "2026-11-21T10:00:00Z",
            "last_seen_at": "2026-11-21T10:00:00Z",
        }
    )
    matches = [match(firms[n], "content", confidence) for n in names]
    req = _req(post, *matches)
    return req.model_copy(update={"register_status": "not_registered", "embed": False})


LISTED = (
    "Dom Maklerski Wisła Capital S.A.",
    "Mazowiecki Bank Inwestycyjny S.A.",
    "Kyrenia Prime Ltd",
)


@pytest.mark.parametrize("classifier", [False, True])
def test_ranking_of_licensed_firms_is_not_shadow_advisory(firms, classifier: bool) -> None:  # type: ignore[no-untyped-def]
    """A comparison of brokers by their registered names describes *their* services (a
    personal manager, the MiFID survey, managed funds): an independent comparison is M1's
    business, never unlicensed advice by the page (docs/eval/LABELING.md)."""
    settings = Settings(ai_mode="rules", classifier=classifier)
    out = analyze(_ranking_req(RANKING, firms, *LISTED), settings)
    assert [f.module for f in out.findings] == ["m1_third_party_ad"]


def test_ranking_with_its_own_buy_calls_is_still_shadow_advisory(firms) -> None:  # type: ignore[no-untyped-def]
    """The publisher's own buy / sell call is advice whatever else the page lists."""
    text = RANKING + "Nasz sygnał kupna na ten tydzień: kupuj teraz akcje spółki Orlen.\n"
    out = analyze(_ranking_req(text, firms, *LISTED), RULES)
    assert "m3_shadow_advisory" in {f.module for f in out.findings}


def test_page_naming_one_licensed_firm_keeps_the_m3_gate(firms) -> None:  # type: ignore[no-untyped-def]
    """One firm named (a scam page citing a real broker) is not a comparison of firms."""
    out = analyze(_ranking_req(RANKING, firms, LISTED[0]), RULES)
    assert "m3_shadow_advisory" in {f.module for f in out.findings}


def test_loose_short_name_matches_are_not_a_listing(firms) -> None:  # type: ignore[no-untyped-def]
    """Common words matched as short brand names ("Shares", "dealing") are not a page that
    lists firms by their registered names: the M3 gate stays open."""
    out = analyze(_ranking_req(RANKING, firms, *LISTED, confidence=0.75), RULES)
    assert "m3_shadow_advisory" in {f.module for f in out.findings}


# ------------------------------------- neutral pages that only name licensed firms (unseen pages)

NEUTRAL = (
    "Fundusz inwestycyjny to instytucja wspólnego inwestowania. Fundusze w Polsce tworzą"
    " towarzystwa funduszy inwestycyjnych nadzorowane przez KNF.\n"
    "Na rynku działają m.in. Dom Maklerski Wisła Capital S.A., Mazowiecki Bank Inwestycyjny"
    " S.A. i Kyrenia Prime Ltd. Aktywa funduszu przechowuje depozytariusz.\n"
)


@pytest.mark.parametrize("classifier", [False, True])
def test_m1_without_promotion_markers_stays_below_the_threshold(firms, classifier: bool) -> None:  # type: ignore[no-untyped-def]
    """An encyclopedia / exchange / editorial page that merely names licensed firms is not an
    advertisement: without a single promotion marker M1 keeps a low informational score."""
    settings = Settings(ai_mode="rules", classifier=classifier)
    out = analyze(_ranking_req(NEUTRAL, firms, *LISTED), settings)
    m1 = next(f for f in out.findings if f.module == "m1_third_party_ad")
    assert m1.risk_level == "low"
    assert "brak znaczników promocji" in m1.explanation


@pytest.mark.parametrize("classifier", [False, True])
def test_m1_with_a_promotion_marker_is_not_capped(firms, classifier: bool) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(ai_mode="rules", classifier=classifier)
    text = NEUTRAL + "Załóż konto z mojego linku partnerskiego i użyj kodu promocyjnego WISLA10.\n"
    out = analyze(_ranking_req(text, firms, *LISTED), settings)
    m1 = next(f for f in out.findings if f.module == "m1_third_party_ad")
    assert m1.risk_level == "high"


@pytest.mark.parametrize("classifier", [False, True])
def test_listing_without_personalised_advice_stays_below_the_m3_threshold(  # type: ignore[no-untyped-def]
    firms, classifier: bool
) -> None:
    """A broker ranking with generic buy wording ("Jakie akcje kupić w 2026?") but no advice
    tailored to the reader is not shadow advisory: M3 may report, never at the alert level."""
    settings = Settings(ai_mode="rules", classifier=classifier)
    text = RANKING + "Nasz sygnał kupna na ten tydzień: kupuj teraz akcje spółki Orlen.\n"
    out = analyze(_ranking_req(text, firms, *LISTED), settings)
    m3 = next(f for f in out.findings if f.module == "m3_shadow_advisory")
    assert m3.risk_level == "low"


def test_listing_with_personalised_advice_keeps_the_m3_score(firms) -> None:  # type: ignore[no-untyped-def]
    text = (
        RANKING
        + "Nasz sygnał kupna na ten tydzień: kupuj teraz akcje spółki Orlen.\n"
        + "Napisz do nas, a dobierzemy portfel dopasowany do Twojej sytuacji i Twoich celów.\n"
    )
    out = analyze(_ranking_req(text, firms, *LISTED), RULES)
    m3 = next(f for f in out.findings if f.module == "m3_shadow_advisory")
    assert any(r.rule_id == "76a" and r.status == "fail" for r in m3.rules)
    assert m3.risk_level == "high"


def _plain_req(text: str) -> AnalyzeRequest:
    req = _ranking_req(text, {})
    return req.model_copy(update={"firm_matches": []})


def test_regulator_menu_without_a_promotional_claim_has_no_m2() -> None:
    """A page with no firm and only a bare gain word in its menu is not an advertisement."""
    menu = (
        "Dla konsumenta\nWyszukiwarka podmiotów→Lista ostrzeżeń publicznych KNF→Porównywarka"
        " Wybieram Fundusze→Średnia ważona stopa zwrotu OFE→Informacja dotycząca otwartych"
        " funduszy emerytalnych→\n"
    )
    assert analyze(_plain_req(menu), RULES).findings == []


def test_unmatched_gain_promise_with_a_figure_still_gets_m2() -> None:
    text = "Zarabiaj nawet 30% miesięcznie na naszej platformie inwestycyjnej!\n"
    out = analyze(_plain_req(text), RULES)
    assert [f.module for f in out.findings][:1] == ["m2_risk_disclosure"]


def test_m1_explanation_without_gain_claims_reads_as_polish(firms) -> None:  # type: ignore[no-untyped-def]
    text = NEUTRAL + "Załóż konto z mojego linku partnerskiego.\n"
    out = analyze(_ranking_req(text, firms, *LISTED), RULES)
    m1 = next(f for f in out.findings if f.module == "m1_third_party_ad")
    assert "bez twierdzeń o zysku ani o ryzyku" in m1.explanation
    assert "zysku o ryzyku" not in m1.explanation
