import type { ConnectorInfo, ConnectorStatus, Source } from "@/api/types";

const ACCESS: Record<string, Source["access_mode"]> = {
  web: "crawler",
  site: "crawler",
  manual: "analyst",
  youtube: "official_api",
  meta_ad_library: "official_api",
  tiktok: "official_api",
  sample: "file_import",
};

const DAY = "2026-11-21";
const at = (time: string, day = DAY) => `${day}T${time}:00Z`;

/** Connector status per collector in the demo (no platform keys configured). */
const STATUS: Record<string, ConnectorStatus> = {
  youtube: "ready",
  meta_ad_library: "needs_credentials",
  tiktok: "needs_approval",
};

const source = (
  n: number,
  name: string,
  collector: string,
  platform: Source["platform"],
  target: string,
  cron: string,
  last: { at: string | null; status: Source["last_status"]; items: number },
  enabled = true,
): Source => ({
  id: `s0000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
  name,
  platform,
  collector,
  target,
  url: target,
  module_hint: null,
  cron,
  schedule: cron,
  enabled,
  next_run_at: null,
  last_status: last.status,
  last_run_at: last.at,
  last_run_status:
    last.status === "blocked" ? "error" : ((last.status as Source["last_run_status"]) ?? null),
  last_run_items: last.items,
  created_at: at("00:00", "2026-11-20"),
  access_mode: ACCESS[collector] ?? "file_import",
  connector_status: STATUS[collector] ?? "ready",
});

/** Demo sources (fictional `.example` domains, like data/fixtures). */
export const mockSources: Source[] = [
  source(
    1,
    "Strony firm z rejestru KNF",
    "web",
    "web",
    "https://wislacapital.example/",
    "0 4 * * *",
    {
      at: at("03:12"),
      status: "ok",
      items: 1096,
    },
  ),
  source(2, "YouTube", "youtube", "youtube", "filmy o brokerach", "0 */6 * * *", {
    at: at("06:30"),
    status: "ok",
    items: 41,
  }),
  source(
    3,
    "Biblioteka reklam Meta",
    "meta_ad_library",
    "facebook",
    "inwestuj, forex, CFD",
    "0 */6 * * *",
    { at: null, status: null, items: 0 },
  ),
  source(4, "Biblioteka reklam TikTok", "tiktok", "tiktok", "reklamy w UE", "0 */12 * * *", {
    at: null,
    status: null,
    items: 0,
  }),
  source(5, "Import plików", "sample", "sample", "próbki UKNF", "0 4 * * *", {
    at: at("17:40", "2026-11-20"),
    status: "ok",
    items: 58,
  }),
  source(6, "Zgłoszenia analityków", "manual", "web", "adresy z „Sprawdź”", "0 */6 * * *", {
    at: at("02:10"),
    status: "ok",
    items: 24,
  }),
];

const connector = (
  name: string,
  label: string,
  access_mode: ConnectorInfo["access_mode"],
  how_to: string,
  status: ConnectorStatus = "ready",
  requires: string[] = [],
): ConnectorInfo => ({
  name,
  label,
  access_mode,
  status,
  requires,
  how_to,
  legal_basis: "",
  collector: name,
});

/** Demo connectors (`GET /api/connectors`), mirroring `collectors/policy.py`. */
export const mockConnectors: ConnectorInfo[] = [
  connector("web", "Strony WWW (crawler InvestWatchBot)", "crawler", "Działa bez klucza."),
  connector("site", "Strony firm z rejestru KNF (sitemap.xml)", "crawler", "Działa bez klucza."),
  connector("youtube", "YouTube (YouTube Data API v3)", "official_api", "Klucz API ustawiony."),
  connector(
    "meta_ad_library",
    "Facebook / Instagram (Meta Ad Library API)",
    "official_api",
    "Potrzebny token Meta Ad Library: potwierdzenie tożsamości na facebook.com/ID i aplikacja deweloperska (kilka dni). Do tego czasu wgraj eksport z Ad Library jako plik.",
    "needs_credentials",
    ["META_AD_LIBRARY_TOKEN"],
  ),
  connector(
    "tiktok",
    "TikTok (Commercial Content API)",
    "official_api",
    "TikTok musi zatwierdzić wniosek o dostęp do Commercial Content API (ok. 2 dni robocze). Do tego czasu wgraj eksport z biblioteki reklam jako plik.",
    "needs_approval",
    ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
  ),
];
