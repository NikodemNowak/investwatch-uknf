"""Inference for the M1 / M3 logistic-regression heads (numpy only, weights in JSON).

`make train` writes `weights/<module>.json`; this module only reads them. Each head has two
variants: `embedding` (lexicon features + bge-m3 vector) and `lexicon` (features only), the
fallback when Ollama cannot embed. Both are Platt-calibrated on out-of-fold scores.

Thresholds: the module threshold is the `embedding` variant's train-CV F2 optimum. The
`lexicon` variant's own optimum is mapped onto it by a logit shift, so `score >= threshold`
means the same decision rule whichever variant ran.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from ..config import Settings
from ..schemas import ModuleId
from .features import LABELS_PL, HeadId

WEIGHTS_DIR = Path(__file__).resolve().parent / "weights"
DEFAULT_THRESHOLDS: dict[ModuleId, float] = {
    "m1_third_party_ad": 0.5,
    "m2_risk_disclosure": 0.6,
    "m3_shadow_advisory": 0.5,
}
Variant = Literal["embedding", "lexicon"]


class VariantWeights(BaseModel):
    """One fitted logistic regression plus its Platt calibration."""

    model_config = ConfigDict(extra="forbid")

    features: list[str]
    mean: list[float]
    scale: list[float]
    coef: list[float]
    intercept: float
    emb_mean: list[float] = []
    emb_scale: list[float] = []
    emb_coef: list[float] = []
    platt_a: float
    platt_b: float
    c: float
    """Inverse L2 strength chosen by CV."""
    threshold: float
    """F2-optimal threshold on calibrated out-of-fold probabilities (train split only)."""
    cv: dict[str, float]


class HeadWeights(BaseModel):
    """A trained head (`weights/<module>.json`)."""

    model_config = ConfigDict(extra="forbid")

    module: HeadId
    version: str
    seed: int
    embed_model: str
    trained_on: dict[str, int]
    variants: dict[str, VariantWeights]

    @property
    def threshold(self) -> float:
        """Module threshold: the embedding variant's (or the lexicon one's if none)."""
        v = self.variants.get("embedding") or self.variants["lexicon"]
        return v.threshold


class ThresholdsFile(BaseModel):
    """`weights/thresholds.json`: per-module thresholds chosen on the train split."""

    model_config = ConfigDict(extra="forbid")

    thresholds: dict[ModuleId, float]
    method: str


@dataclass(frozen=True)
class HeadOutput:
    """A head's verdict for one post."""

    probability: float
    variant: Variant
    contributions: list[tuple[str, float]]
    """(feature, logit contribution) sorted by absolute size; `embedding` is one entry."""
    version: str

    def describe(self, top: int = 3) -> str:
        """Polish one-liner for the finding explanation."""
        parts = [
            f"{LABELS_PL.get(name, name)} {value:+.1f}"
            for name, value in self.contributions[:top]
            if abs(value) >= 0.05
        ]
        source = "embedding bge-m3 + leksykon" if self.variant == "embedding" else "leksykon"
        return (
            f"Klasyfikator ({source}): p = {self.probability:.2f}"
            + (f"; wkład w logit: {', '.join(parts)}" if parts else "")
            + "."
        )


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


@cache
def load_head(module: HeadId, weights_dir: Path = WEIGHTS_DIR) -> HeadWeights | None:
    """The trained head, or None when `make train` has not produced it."""
    path = weights_dir / f"{module}.json"
    if not path.exists():
        return None
    return HeadWeights.model_validate_json(path.read_text(encoding="utf-8"))


@cache
def trained_thresholds(weights_dir: Path = WEIGHTS_DIR) -> dict[ModuleId, float]:
    """Thresholds from `make train` (empty when absent)."""
    path = weights_dir / "thresholds.json"
    if not path.exists():
        return {}
    return dict(ThresholdsFile.model_validate_json(path.read_text(encoding="utf-8")).thresholds)


def weights_dir(settings: Settings) -> Path:
    """Where the trained weights live for these settings."""
    return Path(settings.classifier_dir) if settings.classifier_dir else WEIGHTS_DIR


def module_thresholds(settings: Settings) -> dict[ModuleId, float]:
    """Environment override, else the trained threshold, else the built-in default.

    The M2 threshold is a rule-score cut chosen on the train split and applies even when the
    heads are switched off; the M1 / M3 ones belong to the heads.
    """
    trained = dict(trained_thresholds(weights_dir(settings)))
    if not settings.classifier:
        trained = {k: v for k, v in trained.items() if k == "m2_risk_disclosure"}
    env: dict[ModuleId, float | None] = {
        "m1_third_party_ad": settings.threshold_m1,
        "m2_risk_disclosure": settings.threshold_m2,
        "m3_shadow_advisory": settings.threshold_m3,
    }
    out: dict[ModuleId, float] = {}
    for module, default in DEFAULT_THRESHOLDS.items():
        value = env[module]
        out[module] = value if value is not None else trained.get(module, default)
    return out


def _raw_logit(
    v: VariantWeights, features: dict[str, float], embedding: np.ndarray | None
) -> tuple[float, list[tuple[str, float]]]:
    x = np.array([features.get(f, 0.0) for f in v.features])
    xs = (x - np.asarray(v.mean)) / np.asarray(v.scale)
    parts = np.asarray(v.coef) * xs
    contributions = [(f, float(c) * v.platt_a) for f, c in zip(v.features, parts, strict=True)]
    z = v.intercept + float(parts.sum())
    if embedding is not None and v.emb_coef:
        es = (embedding - np.asarray(v.emb_mean)) / np.asarray(v.emb_scale)
        e = float(np.dot(np.asarray(v.emb_coef), es))
        z += e
        contributions.append(("embedding", e * v.platt_a))
    contributions.sort(key=lambda kv: -abs(kv[1]))
    return z, contributions


def predict(
    head: HeadWeights, features: dict[str, float], embedding: list[float] | None
) -> HeadOutput:
    """Calibrated probability of the head, aligned to the module threshold."""
    variant: Variant = (
        "embedding" if embedding is not None and "embedding" in head.variants else "lexicon"
    )
    v = head.variants[variant]
    emb = np.asarray(embedding, dtype=np.float64) if variant == "embedding" else None
    if emb is not None and emb.shape[0] != len(v.emb_coef):
        variant, v, emb = "lexicon", head.variants["lexicon"], None
    z, contributions = _raw_logit(v, features, emb)
    logit = v.platt_a * z + v.platt_b
    # Align this variant's own CV threshold with the module threshold (no-op for the primary).
    logit += _logit(head.threshold) - _logit(v.threshold)
    return HeadOutput(
        probability=round(_sigmoid(logit), 4),
        variant=variant,
        contributions=contributions,
        version=head.version,
    )


def dump(head: HeadWeights, path: Path) -> None:
    """Write compact JSON (6 significant digits keep the file small)."""

    def round_all(obj: object) -> object:
        if isinstance(obj, float):
            return float(f"{obj:.6g}")
        if isinstance(obj, list):
            return [round_all(x) for x in obj]
        if isinstance(obj, dict):
            return {k: round_all(v) for k, v in obj.items()}
        return obj

    path.write_text(
        json.dumps(round_all(head.model_dump()), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
