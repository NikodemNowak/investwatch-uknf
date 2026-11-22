"""Application settings, read once from environment variables.

Names follow `.env.example` (no prefix), so the same file configures every Compose service.
`APP_DATA_DIR` and `APP_LOG_LEVEL` are still accepted for backwards compatibility.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AiMode = Literal["llm", "rules", "mock"]
"""`llm`: rules now, LLM second opinion later from the `llm` queue; `rules`: no LLM;
`mock`: skip the AI service entirely."""


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


BOT_NAME = "InvestWatchBot"
BOT_VERSION = "1.0"


def default_user_agents(contact_url: str, contact_email: str = "") -> list[str]:
    """The two honest User-Agents: plain bot token and the `compatible` browser-style form."""
    contact = f"+{contact_url}" + (f"; {contact_email}" if contact_email else "")
    return [
        f"{BOT_NAME}/{BOT_VERSION} ({contact})",
        f"Mozilla/5.0 (compatible; {BOT_NAME}/{BOT_VERSION}; +{contact_url})",
    ]


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(
        default=Path("./data"), validation_alias=AliasChoices("APP_DATA_DIR", "DATA_DIR")
    )
    log_level: str = Field(
        default="INFO", validation_alias=AliasChoices("APP_LOG_LEVEL", "LOG_LEVEL")
    )

    database_url: str = ""
    """Full SQLAlchemy URL; overrides the `POSTGRES_*` parts when set (tests use SQLite)."""
    postgres_user: str = "investwatch"
    postgres_password: str = "investwatch"
    postgres_db: str = "investwatch"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_url: str = "redis://localhost:6379/0"
    celery_eager: bool = False
    """Run Celery tasks inline (tests and single-process dev)."""
    celery_queue_order: Literal["round_robin", "priority"] = "round_robin"
    """How a worker picks between its queues: `priority` always drains them in `-Q` order
    (`worker-llm`: `llm_priority` before `llm`); `round_robin` takes turns."""
    realtime_backend: Literal["redis", "memory"] = "redis"
    """`memory` keeps Socket.IO in-process (tests); `redis` shares it with the workers."""

    storage_backend: Literal["minio", "memory"] = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "investwatch"
    minio_root_password: str = "investwatch-secret"
    minio_bucket: str = "investwatch"
    minio_secure: bool = False

    ai_url: str = "http://localhost:8001"
    ai_mode: AiMode = "llm"
    ai_timeout_s: float = 60.0
    """Fast pass (rules + embedding): no LLM call, so this is generous."""
    llm_review_timeout_s: float = 100.0
    """HTTP timeout of the LLM pass; the `ai` service enforces its own 90 s budget inside."""
    llm_review_retry_s: float = 120.0
    """Delay before retrying a review the model could not give (Ollama down, model pulling)."""
    llm_review_max_retries: int = 3
    embed_backfill_batch: int = 16
    """Posts embedded per `embed_missing_posts` run (seeded posts never pass the pipeline)."""
    llm_model: str = "gemma4:e2b-it-qat"
    embed_model: str = "bge-m3"

    collector_contact_url: str = "https://github.com/NikodemNowak/investwatch-uknf"
    """Where a site owner learns who crawls them; part of every User-Agent."""
    collector_contact_email: str = ""
    """Optional contact e-mail added to the User-Agent."""
    collector_user_agents: str = ""
    """Optional pool separated by `|`; each entry must identify `InvestWatchBot`.

    Empty = the two default InvestWatchBot User-Agents. Rotation spreads load across agents
    that all name the bot; it is never used to hide who is fetching or to retry a refusal."""
    collector_proxy_urls: str = ""
    """Comma-separated egress proxies (round-robin); empty means direct. The per-domain limit
    and the cooldown after a refusal apply whatever proxy is used."""
    collector_min_interval_s: float = 2.0
    """Minimum delay between two requests to the same domain (a longer `Crawl-delay` wins)."""
    collector_cooldown_s: float = 3600.0
    """After a 401/403/429 the domain is not contacted again for this long (or `Retry-After`)."""
    collector_timeout_s: float = 20.0
    render_enabled: bool = True
    """Render pages in headless Chromium (RenderSnapshot + screenshots); off = HTTP text only."""
    render_timeout_s: float = 30.0
    platform_max_items: int = 5
    """Items per run for YouTube / Meta / TikTok / site sources unless the target says `N:`."""

    youtube_api_key: str = ""
    """YouTube Data API v3 key (Google Cloud project). Empty = `youtube` needs credentials."""
    youtube_daily_units: int = 9000
    """Hard stop below Google's default 10,000 units/day quota (search = 100, videos = 1)."""
    meta_ad_library_token: str = ""
    """Meta Ad Library API token (identity-verified account + developer app)."""
    meta_graph_version: str = "v25.0"
    meta_ad_library_country: str = "PL"
    meta_ad_type: str = "ALL"
    """`ALL` or `FINANCIAL_PRODUCTS_AND_SERVICES_ADS` (`ad_type` of `ads_archive`)."""
    microsoft_ad_library_enabled: bool = True
    """Microsoft Ad Library API (public, no key): ads served on Bing in the EEA."""
    microsoft_ad_library_country: int = 151
    """Country id of the Ad Library API (151 = Poland)."""
    microsoft_ad_library_details: int = 4
    """Ads per run whose details (dates, payer, impressions by country) are read: 1 call each."""
    microsoft_ad_library_interval_s: float = 8.0
    """Seconds between two API calls (unauthenticated calls are throttled; 429 after a burst)."""
    microsoft_ad_library_max_wait_s: float = 120.0
    """A throttle pause up to this long is waited out; a longer one fails the run (cache first)."""
    microsoft_ad_library_follow: int = 5
    """Landing pages (`DestinationUrl`) per run handed to the crawler; 0 = none."""
    microsoft_ad_library_cache_ttl_s: int = 6 * 3600
    """A search answer is reused this long; an empty answer (throttling) falls back to it."""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    """TikTok Commercial Content API client credentials (approved developer application)."""

    commoncrawl_enabled: bool = True
    """Optional URL discovery from the Common Crawl index (cached; failures are soft)."""
    commoncrawl_index: str = ""
    """Index id such as `CC-MAIN-2026-44`; empty = the newest one from `collinfo.json`."""
    gdelt_enabled: bool = False
    """Optional news discovery via the GDELT DOC API (1 query / 5 s, citation required)."""
    site_url_keywords: str = (
        "promocj,oferta,konto,bonus,kampani,inwest,kod,polec,partner,rachunek,lokat,fundusz"
    )
    """Comma-separated URL fragments that make a sitemap URL worth checking (`site`)."""
    seed_live_sources: bool = True
    """`python -m investwatch.seed` also adds the curated live sources (YouTube, Meta, ...)."""
    check_allowed_internal_hosts: str = "demo-sites"
    """Private hosts `POST /api/check` may fetch (SSRF guard), comma-separated."""

    registry_live_sync: bool = True
    """Daily Beat task fetches the KNF register live (falls back to the snapshot offline)."""
    registry_extra_firms: str = "fixtures/firms.json,registry/demo_firms.json"
    """Fictional firms (paths relative to the data dir, merged by id); empty disables them."""
    registry_user_agent: str = (
        "InvestWatchBot/1.0 (+https://github.com/NikodemNowak/investwatch-uknf; KNF register sync)"
    )
    registry_request_interval_s: float = 1.0
    """Politeness delay between two requests to knf.gov.pl."""

    near_duplicate_cosine: float = 0.97
    cors_origins: str = "http://localhost:8080,http://localhost:8000,http://localhost:5173"

    @field_validator("collector_user_agents")
    @classmethod
    def _honest_agents(cls, value: str) -> str:
        """Refuse a pool with any agent that does not name the bot (no browser disguise)."""
        for agent in (ua.strip() for ua in value.split("|")):
            if agent and BOT_NAME not in agent:
                raise ValueError(
                    f"every entry must contain {BOT_NAME} (browser-like agents are not allowed)"
                )
        return value

    @property
    def sqlalchemy_url(self) -> str:
        """Return the database URL, built from the `POSTGRES_*` parts unless overridden."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def fixtures_dir(self) -> Path:
        """Return the directory with contract fixtures."""
        return self.data_dir / "fixtures"

    @property
    def registry_dir(self) -> Path:
        """Return the directory with the committed KNF register snapshot."""
        return self.data_dir / "registry"

    @property
    def registry_extra_paths(self) -> list[Path]:
        """Return the fictional-firm files to load next to the register."""
        return [self.data_dir / p for p in _split_csv(self.registry_extra_firms)]

    @property
    def user_agents(self) -> list[str]:
        """Return the User-Agent pool (every entry identifies InvestWatchBot)."""
        pool = [ua.strip() for ua in self.collector_user_agents.split("|") if ua.strip()]
        return pool or default_user_agents(self.collector_contact_url, self.collector_contact_email)

    @property
    def url_keywords(self) -> list[str]:
        """Return the sitemap URL keywords of the `site` collector."""
        return [k.lower() for k in _split_csv(self.site_url_keywords)]

    @property
    def proxy_urls(self) -> list[str]:
        """Return the proxy pool."""
        return _split_csv(self.collector_proxy_urls)

    @property
    def allowed_internal_hosts(self) -> list[str]:
        """Return hosts exempt from the SSRF guard."""
        return _split_csv(self.check_allowed_internal_hosts)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return allowed CORS origins."""
        return _split_csv(self.cors_origins)


class ConfigError(SystemExit):
    """Invalid environment: exits with one readable line instead of a validation traceback."""


_FIXES: dict[str, str] = {
    "collector_user_agents": "leave it empty or copy the COLLECTOR_USER_AGENTS line from "
    ".env.example into your .env",
}


def config_error(exc: ValidationError) -> ConfigError:
    """One-line message naming the bad variable(s) and how to fix them."""
    parts = []
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else ""
        message = str(error["msg"]).removeprefix("Value error, ")
        fix = _FIXES.get(field, "see .env.example")
        parts.append(f"{field.upper()}: {message}; fix: {fix}")
    return ConfigError("Invalid configuration: " + " | ".join(parts))


@cache
def get_settings() -> Settings:
    """Return the cached settings instance (exits with a one-line error when invalid)."""
    try:
        return Settings()
    except ValidationError as exc:
        raise config_error(exc) from None
