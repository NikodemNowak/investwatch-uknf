"""Service settings, read once from the environment."""

from __future__ import annotations

from functools import cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

AiMode = Literal["rules", "llm", "mock"]
"""rules: regex + lexicon only; llm: rules plus Ollama review; mock: deterministic, no network."""


class Settings(BaseSettings):
    """Environment configuration (names match docker-compose / .env)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ollama_url: str = "http://ollama:11434"
    llm_model: str = "gemma4:e2b-it-qat"
    embed_model: str = "bge-m3"
    ai_mode: AiMode = "llm"
    llm_timeout_s: float = 90.0
    """Hard budget per LLM call, retries included (roadmap 2.2)."""
    embed_timeout_s: float = 30.0
    embed_enabled: bool = True
    """False: never call Ollama for bge-m3 (lite stack without models). Posts get no embedding,
    `/embed` answers 503 and the M1 / M3 heads use their lexicon variant."""
    llm_retries: int = 3
    llm_backoff_s: float = 0.5
    threshold_m1: float | None = None
    threshold_m2: float | None = None
    threshold_m3: float | None = None
    """None: use the threshold `make train` chose on the train split (built-in default 0.5 /
    0.6 / 0.5 when no trained file exists)."""
    classifier: bool = True
    """Use the trained M1 / M3 heads and their thresholds; false = rules and lexicon only."""
    classifier_dir: str | None = None
    """Directory with the trained weights (default: the committed `classifier/weights/`)."""


@cache
def get_settings() -> Settings:
    """Return the process-wide settings."""
    return Settings()
