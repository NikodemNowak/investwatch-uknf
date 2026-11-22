# data/golden/

Labelling set for calibration. Rebuilt on 2026-11-21 under ADR 0008 (official access only).

`raw/posts.jsonl` (86 rows, one JSON object per line, `access_mode` on every row):

| Part | Rows | How it was obtained | What is kept |
|---|---|---|---|
| Web pages, M1/M2 and register firms | 24 | URLs first found by an earlier search-engine run, now treated as the analyst's seed list (`discovered_by: analyst_seed`) and re-fetched on 2026-11-21 by the compliant crawler (`InvestWatchBot`, robots.txt, TDM reservations) | URL, label, page text (max 20,000 chars) |
| Web pages, M3, entities outside the KNF register | 21 | same re-fetch | URL and label only (`text` empty): naming a firm as possible shadow advisory in a public repository is a personal-rights and copyright risk |
| YouTube | 41 | originally collected with yt-dlp (removed) | video id, URL, label only. Restore the text through the official API: `cd backend && uv run python -m investwatch.collectors.hydrate ../data/golden/raw/posts.jsonl --out /tmp/golden.jsonl` (needs `YOUTUBE_API_KEY`; keep the output outside the repo, at most 30 days) |

Removed from the file: 64 Meta ads (33 Facebook, 31 Instagram) taken from the Ad Library web page
without an API token, 7 TikTok videos parsed from TikTok pages, and 1 Google Play page (platform
host); their 29 lines in `labels/real.jsonl` were removed with them. None of them can be re-obtained through an allowed path before the deadline. The old file
is still in git history (`a44af71`); rewriting history is the team lead's decision and is
recommended before the repository is published or handed to UKNF.

`golden.jsonl` keeps an item for every remaining label (179). `make eval` scores only items with
text: the 41 YouTube ids and 21 M3 pages without text are listed as "not scored" in
`docs/eval/latest.md` until the YouTube rows are hydrated locally.
