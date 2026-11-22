"""Generate extra Polish training texts with a local LLM (train split only, never evaluated).

Usage (from `ai/`, Ollama running with the model pulled):
    uv run python -m investwatch_ai.classifier.augment --model gemma3:4b --per-spec 6

Writes `data/golden/augment/llm_train.jsonl`: one item per line with `provenance.collector =
"generator:llm"` and the model name. `make train` adds these rows to the training folds only;
they never enter the golden set, its splits or any reported metric.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..llm import LLMError, OllamaClient

log = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "data" / "golden" / "augment" / "llm_train.jsonl"

Module = Literal["m1_third_party_ad", "m3_shadow_advisory"]


@dataclass(frozen=True)
class Spec:
    """One kind of text to generate."""

    id: str
    module: Module
    label: int
    brief: str


FIRMS = (
    "Nordbrok, Sowa Maklerska, Odra Markets, Bałtyk Securities, Tatra Fundusze, Pilica Inwestycje"
)
"""Fictional firm names (same as the synthetic generator), so no real firm is implicated."""

SPECS: tuple[Spec, ...] = (
    # M1 hard positives: disguised third-party promotion of an investment firm.
    Spec(
        "m1-pos-story",
        "m1_third_party_ad",
        1,
        "wpis influencera opowiadający osobistą historię inwestowania, w którym naturalnie "
        "wplata link polecający lub kod do założenia konta w jednej z firm; bez oznaczenia reklamy",
    ),
    Spec(
        "m1-pos-bonus",
        "m1_third_party_ad",
        1,
        "krótki post na Instagramie lub TikToku zachęcający do założenia konta w firmie "
        "inwestycyjnej dla bonusu, darmowych akcji lub pieniędzy na start",
    ),
    Spec(
        "m1-pos-labelled",
        "m1_third_party_ad",
        1,
        "opis filmu na YouTube z segmentem sponsorowanym przez firmę inwestycyjną, z linkiem "
        "partnerskim w opisie i oznaczeniem współpracy",
    ),
    Spec(
        "m1-pos-ranking",
        "m1_third_party_ad",
        1,
        "fragment bloga z 'rankingiem' brokerów, który w praktyce promuje jedną firmę przez "
        "link afiliacyjny i obietnicę zysków",
    ),
    Spec(
        "m1-pos-telegram",
        "m1_third_party_ad",
        1,
        "wiadomość na kanale Telegram namawiająca do rejestracji u brokera przez link "
        "polecający, z obietnicą wysokich zysków",
    ),
    # M1 hard negatives: the firm is mentioned but nothing is promoted.
    Spec(
        "m1-neg-news",
        "m1_third_party_ad",
        0,
        "rzetelna notka prasowa o wynikach finansowych lub zmianie zarządu firmy inwestycyjnej",
    ),
    Spec(
        "m1-neg-complaint",
        "m1_third_party_ad",
        0,
        "post klienta skarżącego się na obsługę, opłaty lub awarię aplikacji firmy inwestycyjnej",
    ),
    Spec(
        "m1-neg-education",
        "m1_third_party_ad",
        0,
        "edukacyjny wpis o tym, jak porównywać opłaty brokerów, wymieniający firmę bez linków "
        "polecających ani kodów",
    ),
    Spec(
        "m1-neg-scam-journalism",
        "m1_third_party_ad",
        0,
        "artykuł dziennikarski ostrzegający przed fałszywymi reklamami podszywającymi się pod "
        "firmę inwestycyjną, cytujący treść oszustwa",
    ),
    Spec(
        "m1-neg-other-ad",
        "m1_third_party_ad",
        0,
        "post reklamujący produkt niezwiązany z finansami (kosmetyki, ubrania), w którym firma "
        "inwestycyjna pojawia się tylko w luźnej wzmiance",
    ),
    Spec(
        "m1-neg-job", "m1_third_party_ad", 0, "ogłoszenie o pracy lub stażu w firmie inwestycyjnej"
    ),
    # M3 hard positives: shadow advisory.
    Spec(
        "m3-pos-group",
        "m3_shadow_advisory",
        1,
        "oferta płatnej grupy lub kanału, w którym autor mówi uczestnikom, które konkretne "
        "akcje lub ETF-y kupić i kiedy sprzedać",
    ),
    Spec(
        "m3-pos-personal",
        "m3_shadow_advisory",
        1,
        "oferta indywidualnych konsultacji, w których osoba bez licencji dobiera portfel "
        "instrumentów finansowych do sytuacji i celów klienta",
    ),
    Spec(
        "m3-pos-management",
        "m3_shadow_advisory",
        1,
        "propozycja zarządzania cudzymi pieniędzmi na rachunku maklerskim klienta w zamian za "
        "procent od zysku",
    ),
    Spec(
        "m3-pos-subtle",
        "m3_shadow_advisory",
        1,
        "subtelny post 'mentora finansowego' oferującego płatne przeglądy portfela z "
        "konkretnymi rekomendacjami kupna lub sprzedaży, bez używania słowa doradztwo",
    ),
    # M3 hard negatives: looks like advice but is not.
    Spec(
        "m3-neg-education",
        "m3_shadow_advisory",
        0,
        "rzetelny materiał edukacyjny o dywersyfikacji i ETF-ach z zastrzeżeniem, że nie "
        "stanowi rekomendacji",
    ),
    Spec(
        "m3-neg-own-portfolio",
        "m3_shadow_advisory",
        0,
        "bloger pokazuje własny portfel i swoje transakcje, wyraźnie bez sugerowania, co mają "
        "kupić czytelnicy",
    ),
    Spec(
        "m3-neg-commentary",
        "m3_shadow_advisory",
        0,
        "ogólny komentarz rynkowy o stopach procentowych i inflacji, bez wskazań kup/sprzedaj",
    ),
    Spec(
        "m3-neg-tax",
        "m3_shadow_advisory",
        0,
        "oferta doradcy podatkowego lub biura rachunkowego dotycząca rozliczenia PIT-38",
    ),
    Spec(
        "m3-neg-journalism",
        "m3_shadow_advisory",
        0,
        "artykuł ostrzegający przed nielicencjonowanymi 'sygnałami' i grupami inwestycyjnymi, "
        "opisujący ich metody",
    ),
    Spec(
        "m3-neg-property",
        "m3_shadow_advisory",
        0,
        "oferta doradztwa przy zakupie nieruchomości lub kredytu hipotecznego",
    ),
)

SYSTEM = (
    "Jesteś generatorem realistycznych polskich tekstów do zbioru treningowego systemu "
    "nadzoru rynku finansowego. Piszesz naturalną polszczyzną, różnym stylem (formalnym, "
    "potocznym, z emoji lub bez), o różnej długości (1 do 6 zdań). Używaj wyłącznie fikcyjnych "
    f"firm: {FIRMS}. Nie wymyślaj prawdziwych nazwisk. Odpowiadasz wyłącznie JSON-em."
)


class _Batch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    texts: list[str]


class AugmentItem(BaseModel):
    """One generated training text."""

    model_config = ConfigDict(extra="forbid")

    id: str
    module: Module
    label: Literal[0, 1]
    text: str
    spec: str
    provenance: dict[str, str]


def generate(client: OllamaClient, model: str, spec: Spec, n: int) -> list[str]:
    """Ask the model for `n` distinct texts of one kind."""
    user = (
        f"Napisz {n} różnych, realistycznych tekstów. Rodzaj: {spec.brief}. "
        'Zwróć JSON: {"texts": ["...", "..."]}.'
    )
    batch = client.chat_json(model, SYSTEM, user, _Batch)
    return [t.strip() for t in batch.texts if len(t.strip()) >= 40]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma3:4b")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--per-spec", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = OllamaClient(args.ollama_url, timeout_s=900.0, retries=2)
    seen: set[str] = set()
    rows: list[AugmentItem] = []
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = AugmentItem.model_validate_json(line)
                rows.append(item)
                seen.add(item.text.casefold())
    for _ in range(args.rounds):
        for spec in SPECS:
            try:
                texts = generate(client, args.model, spec, args.per_spec)
            except LLMError as exc:
                log.warning("%s: %s", spec.id, exc)
                continue
            for text in texts:
                if text.casefold() in seen:
                    continue
                seen.add(text.casefold())
                digest = hashlib.sha256(text.encode()).hexdigest()[:12]
                rows.append(
                    AugmentItem(
                        id=f"llm-{spec.id}-{digest}",
                        module=spec.module,
                        label=1 if spec.label else 0,
                        text=text,
                        spec=spec.id,
                        provenance={
                            "collector": "generator:llm",
                            "model": args.model,
                            "split": "train",
                        },
                    )
                )
            log.info("%s: %d texts (total %d)", spec.id, len(texts), len(rows))
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
