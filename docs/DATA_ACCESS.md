# Data sources and legal compliance

InvestWatch is meant to be used by UKNF, so the default configuration is compliant by
construction ([ADR 0008](decisions/0008-official-data-access.md)):

| Source | Access | Without credentials |
|---|---|---|
| Company websites (KNF register domains, sitemaps) | crawler `InvestWatchBot`: robots.txt, `Crawl-delay`, TDM reservations (art. 26³ pr. aut.), per-domain limit, cooldown after refusal | works |
| KNF registers | public registers, daily sync, 1 request/s; "Źródło: rejestry KNF, stan na <data>" | works |
| YouTube | YouTube Data API v3; data refreshed or deleted within 30 days ([YouTube Terms of Service](https://www.youtube.com/t/terms)) | "wymaga klucza" |
| Facebook / Instagram ads | Meta Ad Library API (DSA art. 39 ad repository) | "wymaga klucza" |
| Bing ads (Microsoft Advertising) | Microsoft Ad Library API (public, EEA ad repository); landing pages through the crawler | works |
| TikTok ads | TikTok Commercial Content API | "wymaga zgody platformy" |
| Analyst files and submissions | `POST /api/imports`, `POST /api/submissions` | works |
| Common Crawl index, GDELT (optional) | open datasets, cached, soft failure | works / off |

We do not log in, bypass blocks, solve captchas or pose as a browser, and we never fetch
Facebook, Instagram, TikTok, YouTube, X or search-engine pages. User-Agent and proxy rotation
(required by the task) exist as mechanisms only: every agent names the bot and a refused request
is never retried through another proxy or agent. `backend/tests/test_compliance.py` fails the
build if a disallowed collector or access path returns. Not legal advice: points marked
"do potwierdzenia" in ADR 0008 need UKNF's legal review.

## Collectors in detail
Social platforms are read only through their official APIs or from files an
analyst imports; company websites are read by a crawler that identifies itself.
`youtube` uses the YouTube Data API v3 (`YOUTUBE_API_KEY`, free, 10,000 units/day; title,
description and tags, no captions). `meta_ad_library` uses the Meta Ad Library API
(`META_AD_LIBRARY_TOKEN`; all ads delivered in Poland, one post per Facebook/Instagram
placement). `tiktok` uses the TikTok Commercial Content API (`TIKTOK_CLIENT_KEY`,
`TIKTOK_CLIENT_SECRET`). A connector without credentials shows "wymaga klucza" or "wymaga
zgody platformy" (`GET /api/connectors`, `connector_status` on every source) and does not run;
there is no fallback to page scraping.
`site` discovers pages of a domain from its sitemap (domains come from the KNF register) and
passes them to `web`, which fetches as `InvestWatchBot`, obeys robots.txt and `Crawl-delay`,
honours TDM reservations, waits at least `COLLECTOR_MIN_INTERVAL_S` per domain and stops for
`COLLECTOR_COOLDOWN_S` after a 403/429. `COLLECTOR_PROXY_URLS` sets the egress proxies; they do
not change the per-domain limit. Platform and search-engine hosts are never fetched.
`microsoft_ad_library` reads the Microsoft Ad Library API
(`GET adlibrary.api.bingads.microsoft.com/api/v1/Ads?searchText=...&countryCodes=151`, Poland).
It is public: no sign-up or key, and Microsoft's guide names researchers and regulators as its
users; unauthenticated calls get stricter limits (24 ads per call, 429 after a burst), so calls
are `MICROSOFT_AD_LIBRARY_INTERVAL_S` (8 s) apart, a short 429 pause is waited out and the call
retried, answers are cached for 6 h and a longer throttle or an
empty answer falls back to the cache. Ads not about investing are dropped (the search also
matches e.g. a fishing reel called "XTB"). The first `MICROSOFT_AD_LIBRARY_DETAILS` ads get
`Ads/{id}?expand=AdDetails` (start/end date, payer, impressions by country). The landing page
(`DestinationUrl`) of the first `MICROSOFT_AD_LIBRARY_FOLLOW` ads goes to the `web` crawler with
every crawler rule; a refusal (robots.txt, 403, TDM) is stored as a `blocked` post with the reason
(`provenance.fetch_error`). Only the API host is contacted; bing.com stays on the deny-list.
Terms: the API guide links Microsoft's general Terms of Use, which do not address the API; they
ask not to overburden servers (hence the spacing and cache) and limit use to personal and
non-commercial use "unless otherwise specified" - the guide's regulator wording is our reading of
"otherwise specified" (do potwierdzenia). Advertisers can be private persons: do not name them
in public material. Platform posts are `platform="bing"`.
Every post carries `provenance` (`access_mode`, `legal_basis`, `fetched_at`, `synthetic`,
`fetch_error`); the UI shows "dane syntetyczne" on fictional material and "firma fikcyjna (demo)"
on fictional firms. `make demo-real` runs the real sources of `data/seeds/real_demo.yaml` live
on top of `make demo`; nothing in it comes from earlier scraping.
`POST /api/imports` loads analyst files (Meta/TikTok exports, UKNF samples); `POST
/api/submissions` records a URL with pasted text. Every post stores how it was obtained
(`raw.access_mode`). Fixtures under `data/fixtures/synthetic/` are synthetic and labelled as
such. Starting sources: `data/seeds/sources.yaml`. Export a run for labelling:
`python -m investwatch.collectors.export --limit 10 --out ../data/golden/raw/posts.jsonl`
(YouTube rows are reduced to ids; `python -m investwatch.collectors.hydrate` restores them).
