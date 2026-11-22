"""Data-access policy: how each connector may reach its source, and which hosts are off limits.

The default configuration is compliant by construction (ADR 0008): social platforms and search
engines are reached only through their official APIs or through files an analyst imports, and
the crawler refuses their hosts outright. Nothing here is configurable through the environment.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

import tldextract
from pydantic import BaseModel

from investwatch.config import BOT_VERSION, Settings

AccessMode = Literal["official_api", "open_dataset", "file_import", "analyst", "crawler"]
"""How a record was obtained; stored on every item as `raw.access_mode`."""
ConnectorStatus = Literal["ready", "needs_credentials", "needs_approval", "disabled"]
"""`ready` runs; the others are shown on the Sources page and never run."""

COLLECTOR_VERSION = BOT_VERSION

PLATFORM_DOMAINS = frozenset(
    {
        "facebook.com", "fb.com", "fb.me", "fb.watch", "instagram.com", "threads.net",
        "threads.com", "messenger.com", "whatsapp.com", "tiktok.com", "tiktokv.com",
        "youtube.com", "youtu.be", "youtube-nocookie.com", "x.com", "twitter.com", "t.co",
        "linkedin.com", "lnkd.in", "bing.com", "duckduckgo.com", "baidu.com", "yahoo.com",
        "startpage.com", "ecosia.org", "qwant.com",
    }
)  # fmt: skip
"""Registrable domains of social platforms and search engines: official APIs only."""
_PLATFORM_LABELS = ("google", "yandex")
"""Search engines with a domain per country (google.pl, google.co.uk, yandex.ru, ...)."""
_PLATFORM_HOSTS = frozenset({"search.brave.com"})
_extract = tldextract.TLDExtract(suffix_list_urls=())


def is_platform_host(host: str) -> bool:
    """True when `host` belongs to a social platform or a search engine."""
    host = host.lower().rstrip(".")
    if not host:
        return False
    if host in _PLATFORM_HOSTS:
        return True
    parts = _extract(host)
    return parts.top_domain_under_public_suffix in PLATFORM_DOMAINS or (
        parts.domain in _PLATFORM_LABELS and bool(parts.suffix)
    )


def platform_rejection(url: str) -> str | None:
    """Why the crawler must not fetch `url` (platform or search-engine host), or None."""
    host = urlsplit(url).hostname or ""
    if is_platform_host(host):
        return f"platform host {host}: official API only"
    return None


class ConnectorInfo(BaseModel):
    """What the Sources page shows about one data source and how it is reached."""

    name: str
    label: str
    access_mode: AccessMode
    status: ConnectorStatus
    requires: list[str] = []
    """Environment variables that must be set for the connector to run."""
    how_to: str
    """How UKNF obtains access (Polish, shown in the UI)."""
    lead_time: str | None = None
    legal_basis: str
    quota: str | None = None
    collector: str | None = None
    """Collector name used by sources, when the connector is one."""


def _api_status(ready: bool, missing: ConnectorStatus) -> ConnectorStatus:
    return "ready" if ready else missing


def connector_infos(settings: Settings) -> list[ConnectorInfo]:
    """Every connector with its current status for `settings`."""
    yt = bool(settings.youtube_api_key)
    meta = bool(settings.meta_ad_library_token)
    tiktok = bool(settings.tiktok_client_key and settings.tiktok_client_secret)
    return [
        ConnectorInfo(
            name="web",
            collector="web",
            label="Strony WWW (crawler InvestWatchBot)",
            access_mode="crawler",
            status="ready",
            how_to="Działa bez klucza. Bot przedstawia się, respektuje robots.txt, Crawl-delay "
            "i zastrzeżenia TDM, po odmowie (403/429) wstrzymuje pobieranie z domeny.",
            legal_basis="art. 26³ pr. aut. (eksploracja tekstów i danych, z poszanowaniem "
            "zastrzeżeń); robots.txt (RFC 9309)",
        ),
        ConnectorInfo(
            name="site",
            collector="site",
            label="Strony firm z rejestru KNF (sitemap.xml)",
            access_mode="crawler",
            status="ready",
            how_to="Działa bez klucza: domeny z rejestru KNF → robots.txt → sitemap.xml → "
            "crawler InvestWatchBot.",
            legal_basis="art. 26³ pr. aut.; robots.txt i mapy witryn publikowane przez właściciela",
        ),
        ConnectorInfo(
            name="manual",
            collector="manual",
            label="Sprawdź URL (strona WWW)",
            access_mode="crawler",
            status="ready",
            how_to="Działa bez klucza. Adresy platform społecznościowych nie są pobierane: "
            "YouTube przez API, pozostałe przez zgłoszenie analityka.",
            legal_basis="jak crawler WWW",
        ),
        ConnectorInfo(
            name="youtube",
            collector="youtube",
            label="YouTube (YouTube Data API v3)",
            access_mode="official_api",
            status=_api_status(yt, "needs_credentials"),
            requires=["YOUTUBE_API_KEY"],
            how_to="Utwórz projekt w Google Cloud, włącz YouTube Data API v3, utwórz klucz API "
            "ograniczony do tego API i wpisz go do .env jako YOUTUBE_API_KEY.",
            lead_time="kilka minut",
            legal_basis="YouTube API Services Terms of Service i Developer Policies "
            "(dane odświeżane lub usuwane po 30 dniach)",
            quota="10 000 jednostek/dzień "
            f"(twardy limit aplikacji: {settings.youtube_daily_units})",
        ),
        ConnectorInfo(
            name="meta_ad_library",
            collector="meta_ad_library",
            label="Facebook / Instagram (Meta Ad Library API)",
            access_mode="official_api",
            status=_api_status(meta, "needs_credentials"),
            requires=["META_AD_LIBRARY_TOKEN"],
            how_to="Potwierdź tożsamość na facebook.com/ID, utwórz aplikację na "
            "developers.facebook.com, wygeneruj token i wpisz go do .env jako "
            "META_AD_LIBRARY_TOKEN. Bez tokenu: import eksportu z Biblioteki reklam.",
            lead_time="od kilku godzin do kilku dni (weryfikacja tożsamości)",
            legal_basis="DSA art. 39 (repozytorium reklam); Meta Platform Terms",
            quota="ok. 200 wywołań/h",
        ),
        ConnectorInfo(
            name="microsoft_ad_library",
            collector="microsoft_ad_library",
            label="Bing (Microsoft Ad Library API)",
            access_mode="official_api",
            status="ready" if settings.microsoft_ad_library_enabled else "disabled",
            how_to="Działa bez klucza: publiczne API repozytorium reklam Microsoft Advertising "
            "(reklamy wyświetlane w Polsce). Strony docelowe reklam pobiera crawler "
            "InvestWatchBot tylko wtedy, gdy robots.txt na to pozwala.",
            legal_basis="DSA art. 39 (repozytorium reklam); Microsoft Ad Library API "
            "(publiczne, przeznaczone także dla regulatorów)",
            quota="bez klucza: do 24 reklam na zapytanie, zapytania co "
            f"{settings.microsoft_ad_library_interval_s:.0f} s, pamięć podręczna "
            f"{settings.microsoft_ad_library_cache_ttl_s // 3600} h",
        ),
        ConnectorInfo(
            name="tiktok",
            collector="tiktok",
            label="TikTok (Commercial Content API)",
            access_mode="official_api",
            status=_api_status(tiktok, "needs_approval"),
            requires=["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
            how_to="Załóż konto TikTok for Developers (służbowy e-mail), złóż wniosek o "
            "Commercial Content API i wpisz klucze aplikacji do .env. Do czasu zgody: import "
            "eksportu z biblioteki reklam TikTok lub zgłoszenie analityka.",
            lead_time="ok. 2 dni robocze (decyzja TikTok)",
            legal_basis="DSA art. 39 (repozytorium reklam); TikTok Developer Terms",
        ),
        ConnectorInfo(
            name="sample",
            collector="sample",
            label="Próbki danych (pliki)",
            access_mode="file_import",
            status="ready",
            how_to="Pliki z data/fixtures lub próbki UKNF w data/samples/.",
            legal_basis="dane przekazane przez organizatora / UKNF",
        ),
        ConnectorInfo(
            name="file_import",
            label="Import pliku (eksport Ad Library, TikTok, próbki UKNF)",
            access_mode="file_import",
            status="ready",
            how_to="Przycisk „Dodaj źródło” → „Import pliku”: plik CSV/JSON/JSONL; zapisywane są "
            "skrót SHA-256, autor importu i opis pochodzenia.",
            legal_basis="materiał dostarczony przez analityka",
        ),
        ConnectorInfo(
            name="analyst",
            label="Zgłoszenie analityka (URL + treść)",
            access_mode="analyst",
            status="ready",
            how_to="Przycisk „Zgłoś materiał”: adres, wklejona treść i opcjonalny zrzut ekranu. "
            "Jedyna droga dla organicznych postów z Facebooka, Instagrama i TikToka.",
            legal_basis="materiał zebrany ręcznie przez pracownika UKNF",
        ),
        ConnectorInfo(
            name="knf_registry",
            label="Rejestry KNF (knf.gov.pl)",
            access_mode="crawler",
            status="ready" if settings.registry_live_sync else "disabled",
            how_to="Codzienna synchronizacja (robots.txt knf.gov.pl pozwala, 1 żądanie/s); "
            "bez sieci: snapshot w data/registry/.",
            legal_basis="informacja sektora publicznego (ustawa o otwartych danych); "
            "źródło: KNF, z datą pobrania",
        ),
        ConnectorInfo(
            name="commoncrawl",
            label="Common Crawl (indeks URL)",
            access_mode="open_dataset",
            status="ready" if settings.commoncrawl_enabled else "disabled",
            how_to="Opcjonalne uzupełnienie listy adresów domeny; wyniki w pamięci podręcznej "
            "7 dni, błąd serwera nie przerywa przebiegu.",
            legal_basis="Common Crawl Terms of Use",
        ),
        ConnectorInfo(
            name="gdelt",
            label="GDELT (wiadomości)",
            access_mode="open_dataset",
            status="ready" if settings.gdelt_enabled else "disabled",
            how_to="Włącz GDELT_ENABLED=true; 1 zapytanie na 5 s, wymagane cytowanie GDELT.",
            legal_basis="GDELT: unlimited and unrestricted use with citation",
        ),
    ]


def connector_status(name: str, settings: Settings) -> ConnectorInfo | None:
    """The connector registered under `name` (collector or connector name), or None."""
    for info in connector_infos(settings):
        if name in (info.name, info.collector):
            return info
    return None


REMOVED_REASON = "Źródło usunięte – niezgodne z zasadami pozyskiwania danych"
"""Why a source whose collector was removed (ADR 0008) never runs (Polish, shown in the UI)."""


def removed_connector(collector: str) -> ConnectorInfo:
    """Connector shown for a collector that no longer exists (old `search`/`discovery` rows)."""
    return ConnectorInfo(
        name=collector,
        collector=collector,
        label=collector,
        access_mode=access_mode_of(collector),
        status="disabled",
        how_to=REMOVED_REASON,
        legal_basis="brak (źródło usunięte, ADR 0008)",
    )


def source_connector(collector: str, settings: Settings) -> ConnectorInfo | None:
    """Connector of a source's collector; removed collectors come back `disabled`."""
    # Imported here: the registry imports the collectors, which import this module.
    from investwatch.collectors.registry import COLLECTORS

    if collector not in COLLECTORS:
        return removed_connector(collector)
    return connector_status(collector, settings)


def collector_ready(collector: str, settings: Settings) -> ConnectorInfo | None:
    """None when `collector` may run; otherwise its connector (status not `ready`)."""
    info = source_connector(collector, settings)
    return info if info is not None and info.status != "ready" else None


def access_mode_of(collector: str) -> AccessMode:
    """Access mode of a collector name (unknown names are file/fixture replays)."""
    modes: dict[str, AccessMode] = {
        "web": "crawler",
        "site": "crawler",
        "manual": "crawler",
        "youtube": "official_api",
        "meta_ad_library": "official_api",
        "tiktok": "official_api",
        "microsoft_ad_library": "official_api",
        "analyst": "analyst",
        "file_import": "file_import",
        "sample": "file_import",
    }
    return modes.get(collector, "file_import")


_LEGAL_BASIS: dict[str, str] = {
    "web": "art. 26³ pr. aut. (TDM, zastrzeżenia respektowane); robots.txt",
    "site": "art. 26³ pr. aut. (TDM, zastrzeżenia respektowane); robots.txt, sitemap.xml",
    "manual": "art. 26³ pr. aut. (TDM, zastrzeżenia respektowane); robots.txt",
    "youtube": "YouTube Data API v3 (YouTube API Services Terms)",
    "meta_ad_library": "DSA art. 39 / Meta Ad Library API (Meta Platform Terms)",
    "tiktok": "DSA art. 39 / TikTok Commercial Content API",
    "microsoft_ad_library": "DSA art. 39 / Microsoft Ad Library API (publiczne)",
    "analyst": "zgłoszenie analityka",
    "file_import": "import pliku przez analityka",
    "sample": "próbki danych od organizatora / UKNF",
}


def legal_basis_of(collector: str) -> str:
    """Short legal basis stored with every record of `collector`."""
    return _LEGAL_BASIS.get(collector, "import pliku przez analityka")
