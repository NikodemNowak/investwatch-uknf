# 0008. Official data access only

Supersedes [0007](0007-platform-collectors-and-robots.md). Not legal advice; items marked
"to be confirmed" need UKNF's legal review.

## Context
The tool is meant for use by UKNF. YouTube's Terms forbid access by automated means outside its
API; Meta's Terms forbid automated collection without permission and facebook.com disallows
crawlers; TikTok's Terms forbid automated extraction not approved by TikTok. No free official web
search API is open to new users (Google's JSON API closes on 1 January 2027, Bing's was retired
in August 2025). ADR 0007 allowed yt-dlp, an opt-in Ad Library page scrape, TikTok page parsing
and DuckDuckGo HTML, with browser-like User-Agents. The task allows "API collectors or content
parsers" with UA and proxy rotation; we choose API collectors.

## Decision
- Platforms: official APIs only (YouTube Data API v3, Meta Ad Library API, TikTok Commercial
  Content API, Microsoft Ad Library API: public, no key, added 2026-11-21), plus file import and analyst submission. A connector without credentials has
  status `needs_credentials` ("wymaga klucza") or `needs_approval` ("wymaga zgody platformy");
  the scheduler skips it and `POST /api/sources/{id}/run` answers 409 with how to get access.
- Websites: a crawler with the `InvestWatchBot/<ver> (+contact)` User-Agent, robots.txt without
  an off switch (rules for `InvestWatchBot`, `Crawl-delay` honoured), TDM reservations honoured
  (`tdm-reservation` header or meta tag, `/.well-known/tdmrep.json`; art. 26³ pr. aut.),
  per-domain rate limit, cooldown after 401/403/429 or a bot challenge, a fixed deny-list of
  platform and search-engine hosts in the fetcher and in the browser renderer (not configurable).
- Discovery: KNF register domains, robots.txt sitemaps and feeds, optional Common Crawl (cached,
  soft failure) and GDELT (off by default). yt-dlp, the Ad Library page scrape, the TikTok parser
  and search-engine discovery are removed.
- UA and proxy rotation stay as mechanisms: every UA identifies the bot (validated at start-up)
  and proxies are an egress choice; a refused request is never retried through another proxy or
  UA, and the per-domain limit and cooldown are shared across proxies.
- Every record stores `access_mode`, `legal_basis`, `collector_version`, fetch time and, for
  imports, the file's SHA-256, who imported it and the stated provenance.
- `backend/tests/test_compliance.py` fails the build if a removed path returns.

## Consequences
Without credentials only websites, the KNF register, imports and the Microsoft Ad Library work
(its landing pages only where robots.txt allows; its terms of use are the general Microsoft
Terms, to be confirmed for scheduled regulatory use); Meta and TikTok show what
is missing. No YouTube captions (they need the owner's OAuth). Organic influencer posts on
Facebook/Instagram/TikTok are covered only by analyst submission until UKNF obtains access from
the platforms (Meta Content Library via a research partner, DSA art. 10 orders; to be
confirmed). M3 coverage depends on the seed list of domains. YouTube data must be refreshed or
deleted within 30 days (weekly `refresh_youtube` task); keeping it longer as evidence needs
UKNF's own legal basis (to be confirmed). The golden set was rebuilt: records obtained by the
removed paths were deleted from the current file. They remain in git history; rewriting history
is the team lead's decision and is recommended before the repository is published or handed to
UKNF. Status 22.11: history not rewritten yet; the records are only in commits before bf8ac48; rewrite before any public release.
