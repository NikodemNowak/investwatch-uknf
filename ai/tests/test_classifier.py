from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from investwatch_ai.analyze import AnalyzeRequest, analyze
from investwatch_ai.classifier import train
from investwatch_ai.classifier.features import extract, feature_names
from investwatch_ai.classifier.model import (
    DEFAULT_THRESHOLDS,
    HeadWeights,
    VariantWeights,
    load_head,
    module_thresholds,
    predict,
)
from investwatch_ai.config import Settings
from investwatch_ai.eval.run import load_golden
from investwatch_ai.rules import M1_RULE_IDS, M3_ELEMENT_IDS, RuleContext, evaluate
from investwatch_ai.schemas import Post

PROMO = "Załóż konto przez mój link polecający i wpisz kod KASIA50, bonus 200 zł na start!"
ADVICE = (
    "W mojej płatnej grupie mówię, które akcje kupić i kiedy sprzedać. Dobiorę portfel do Ciebie."
)


def _ctx_rules(head: str, text: str) -> tuple[RuleContext, list]:  # type: ignore[type-arg]
    ctx = RuleContext.build(text, lang="pl")
    ids = M1_RULE_IDS if head == "m1_third_party_ad" else M3_ELEMENT_IDS
    return ctx, evaluate(ctx, ids)


@pytest.mark.parametrize("head", ["m1_third_party_ad", "m3_shadow_advisory"])
def test_features_cover_every_name_and_stay_in_unit_range(head: str) -> None:
    ctx, rules = _ctx_rules(head, PROMO + " " + ADVICE)
    feats = extract(head, ctx, rules)  # type: ignore[arg-type]
    assert set(feats) == set(feature_names(head))  # type: ignore[arg-type]
    assert all(0.0 <= v <= 1.0 for v in feats.values())


def test_committed_heads_load_with_both_variants() -> None:
    for head in ("m1_third_party_ad", "m3_shadow_advisory"):
        weights = load_head(head)  # type: ignore[arg-type]
        assert weights is not None
        assert set(weights.variants) == {"lexicon", "embedding"}
        assert len(weights.variants["embedding"].emb_coef) == 1024
        assert 0.0 < weights.threshold < 1.0


def test_lexicon_fallback_without_embedding_and_promo_scores_higher() -> None:
    weights = load_head("m1_third_party_ad")
    assert weights is not None
    promo = predict(
        weights, extract("m1_third_party_ad", *_ctx_rules("m1_third_party_ad", PROMO)), None
    )
    plain_text = "Wyniki kwartalne Nordbrok były lepsze od oczekiwań analityków."
    plain = predict(
        weights, extract("m1_third_party_ad", *_ctx_rules("m1_third_party_ad", plain_text)), None
    )
    assert promo.variant == plain.variant == "lexicon"
    assert promo.probability > plain.probability
    assert "Klasyfikator (leksykon)" in promo.describe()


def test_embedding_variant_reports_embedding_contribution() -> None:
    weights = load_head("m3_shadow_advisory")
    assert weights is not None
    vec = np.random.default_rng(0).standard_normal(1024)
    vec /= np.linalg.norm(vec)
    feats = extract("m3_shadow_advisory", *_ctx_rules("m3_shadow_advisory", ADVICE))
    out = predict(weights, feats, [float(x) for x in vec])
    assert out.variant == "embedding"
    assert any(name == "embedding" for name, _ in out.contributions)
    assert 0.0 <= out.probability <= 1.0
    assert "bge-m3" in out.describe()


def test_wrong_embedding_width_falls_back_to_lexicon() -> None:
    weights = load_head("m3_shadow_advisory")
    assert weights is not None
    feats = extract("m3_shadow_advisory", *_ctx_rules("m3_shadow_advisory", ADVICE))
    assert predict(weights, feats, [0.1] * 8).variant == "lexicon"


def test_variant_threshold_maps_onto_module_threshold() -> None:
    def variant(threshold: float) -> VariantWeights:
        return VariantWeights(
            features=["x"],
            mean=[0.0],
            scale=[1.0],
            coef=[1.0],
            intercept=0.0,
            platt_a=1.0,
            platt_b=0.0,
            c=1.0,
            threshold=threshold,
            cv={},
        )

    head = HeadWeights(
        module="m1_third_party_ad",
        version="t",
        seed=0,
        embed_model="m",
        trained_on={},
        variants={"lexicon": variant(0.3), "embedding": variant(0.6)},
    )
    # A lexicon-variant item exactly at its own threshold lands on the module threshold.
    x = float(np.log(0.3 / 0.7))
    out = predict(head, {"x": x}, None)
    assert out.probability == pytest.approx(0.6, abs=1e-3)


def test_threshold_resolution_env_then_trained_then_default() -> None:
    plain = Settings(classifier=False)
    got = module_thresholds(plain)
    assert got["m1_third_party_ad"] == DEFAULT_THRESHOLDS["m1_third_party_ad"]
    assert got["m3_shadow_advisory"] == DEFAULT_THRESHOLDS["m3_shadow_advisory"]
    assert got["m2_risk_disclosure"] == module_thresholds(Settings())["m2_risk_disclosure"]
    override = Settings(threshold_m2=0.42)
    assert module_thresholds(override)["m2_risk_disclosure"] == 0.42
    trained = module_thresholds(Settings())
    assert trained["m1_third_party_ad"] == load_head("m1_third_party_ad").threshold  # type: ignore[union-attr]


def test_m3_head_cannot_open_a_finding_without_embedding(posts: dict[str, Post]) -> None:
    post = posts["01"].model_copy(update={"text": "Dziś na blogu o pogodzie i ogrodzie."})
    req = AnalyzeRequest.model_validate({"post": post.model_dump(mode="json")})
    out = analyze(req, Settings(ai_mode="mock"))
    assert not [f for f in out.findings if f.module == "m3_shadow_advisory"]


def test_training_never_reads_holdout_items() -> None:
    items = load_golden(train.GOLDEN / "golden.jsonl")
    split = {i.id: i.split for i in items}
    rule_labelled = {i.id for i in items if i.labeler == "rule"}
    for head in train.HEADS:
        rows = train.golden_rows(head, items)
        assert rows
        assert {split[r.id] for r in rows} == {"train"}
        assert not [r for r in rows if r.id in rule_labelled]


def test_extra_rows_accept_both_formats_and_skip_non_train(tmp_path: Path) -> None:
    path = tmp_path / "extra.jsonl"
    rows = [
        {"id": "a-1", "module": "m1", "label": 1, "text": PROMO, "provenance": "generator:haiku"},
        {
            "id": "b-1",
            "module": "m1_third_party_ad",
            "label": 0,
            "text": "Notka prasowa.",
            "spec": "m1-neg-news",
            "provenance": {"collector": "generator:llm"},
        },
        {"id": "c-1", "module": "m1", "label": 1, "text": PROMO, "split": "holdout"},
        {"id": "d-1", "module": "m3", "label": 1, "text": ADVICE},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = train.extra_rows("m1_third_party_ad", (path,))
    assert [(r.id, r.source) for r in got] == [("a-1", "generator:haiku"), ("b-1", "generator:llm")]


def test_fit_is_deterministic() -> None:
    texts = [
        PROMO,
        "Wyniki kwartalne były dobre.",
        "Kod BONUS100 i link w bio!",
        "Awaria aplikacji.",
    ]
    rows = [
        train.Row(
            id=f"r{i}",
            label=1 - (i % 2),
            group=f"g{i}",
            source="golden",
            features=extract("m1_third_party_ad", *_ctx_rules("m1_third_party_ad", t)),
            text=t,
        )
        for i in range(20)
        for t in [texts[i % 4]]
    ]
    a = train.fit_variant("m1_third_party_ad", rows, None)
    b = train.fit_variant("m1_third_party_ad", rows, None)
    assert a == b


def test_knf_warning_list_opens_m3_as_a_flag_without_raising_the_score(
    posts: dict[str, Post],
) -> None:
    post = posts["01"].model_copy(update={"text": "Witamy na naszej platformie. Kontakt: biuro."})
    base = {"post": post.model_dump(mode="json")}
    plain = analyze(AnalyzeRequest.model_validate(base), Settings(ai_mode="mock"))
    assert not [f for f in plain.findings if f.module == "m3_shadow_advisory"]
    flagged = analyze(
        AnalyzeRequest.model_validate(base | {"knf_warning": "Example Ltd"}),
        Settings(ai_mode="mock"),
    )
    m3 = next(f for f in flagged.findings if f.module == "m3_shadow_advisory")
    assert m3.score < 0.5  # the visible text has no advice element
    assert "liście ostrzeżeń publicznych KNF" in m3.explanation
