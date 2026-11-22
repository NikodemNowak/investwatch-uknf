# 0007. Platform collectors: access paths and robots.txt

**Status: superseded by [0008](0008-official-data-access.md).** yt-dlp, the Ad Library page
scrape, TikTok page parsing and search-engine discovery described below were removed.

## Context
The task asks for collection from the web and social media (Facebook, Instagram, TikTok) with
UA and proxy rotation. Plan 4.4 commits us to public content only, no logins, no captcha or
bot-check bypass, robots.txt by default and ≥2 s per domain. Measured on 2026-11-21:
facebook.com/robots.txt is `Disallow: /` for generic agents; youtube.com disallows `/results`
and `/youtubei/`; tiktok.com disallows `/search`; html.duckduckgo.com allows everything.
Plain HTTP to the Ad Library returns 403 (the page needs JavaScript); TikTok video pages serve
their data as embedded JSON; yt-dlp's TikTok extractor must solve a JS bot challenge.

## Decision
- `web`, `search`, `tiktok`: every page goes through `PoliteFetcher` (robots.txt, per-domain
  interval shared in Redis, UA pool, proxy pool). TikTok search is not used; videos are
  discovered with `site:tiktok.com` queries. yt-dlp is not used for TikTok.
- `youtube`: yt-dlp, metadata and subtitles only. Watch/channel/playlist pages are checked
  against robots.txt. Search uses yt-dlp by default (the plan's reliable source);
  `YOUTUBE_SEARCH=discovery` keeps search strictly robots-compliant via `site:youtube.com`.
- `meta_ad_library`: the official API when `META_AD_LIBRARY_TOKEN` is set. Without a token the
  source is reported `blocked` unless an operator sets `META_AD_LIBRARY_SCRAPE=true`, a
  deliberate opt-in for the public DSA art. 39 repository (Playwright page load, ads read from
  embedded JSON; single ads via yt-dlp `facebook:ads`).
- Discovery: DuckDuckGo HTML by default; it soft-blocks bursts with a bot check, which we
  report as `blocked` and do not solve. Results are cached (12 h). A self-hosted SearXNG
  (`SEARCH_BACKEND=searxng`) is the on-premise alternative.
- UA and proxy rotation feed httpx, yt-dlp and Playwright alike. They spread load; they are not
  used to get around a block.

## Consequences
Out of the box (no token, no opt-in) Meta sources show as `blocked` on the Sources page, which
is honest and points to the fix. UKNF as a supervisor can obtain the API token. Discovery can
be blocked for a while after bursts; the cache and SearXNG mitigate it.
