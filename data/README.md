# data/

Committed data of InvestWatch. Everything is either an official public register, an official API
response, a page fetched by our robots.txt-respecting crawler (`InvestWatchBot`), or clearly labelled
synthetic material (fictional firms, `.example` domains, `"synthetic": true`). Everything else under
`data/` (caches, `data/samples/`, `.env`-style local files) is git-ignored.

| Folder | What | Source / licence |
|---|---|---|
| `registry/` | KNF registers, KNF public warnings list, brand aliases, fictional demo firms | KNF public sector information (re-use with source and retrieval date); `brands.json`, `demo_firms.json` are ours |
| `golden/` | Labelled evaluation set (`make eval`) and its raw material | mix of synthetic, demo-site, official-register and robots-respecting crawl data; see below and `golden/README.md` |
| `fixtures/` | Test and demo fixtures, trimmed KNF register HTML, synthetic API-shaped records | fictional or public register entries; see `fixtures/README.md` |
| `seeds/` | Source lists loaded by the `seed` service and `make demo-real` | ours (configuration); only official APIs, imports and the honest crawler |
| `demo/` | Nine synthetic social posts for `make demo` | synthetic, fictional authors and firms |

Own code and data are released under the repository licence; third-party public data keeps the
terms stated above. Small test fixtures stay in `data/fixtures/` (committed, < 1 MB total).

`data/registry/` (committed): `knf_registry.json` is the parsed snapshot of the four KNF
investment-firm registers (attachment 1, public data from knf.gov.pl, fetch date inside);
`brands.json` adds well-known brand domains/aliases the register lacks; `demo_firms.json` holds the
fictional firms of `demo-sites/` (merged by id with `fixtures/firms.json`). Refresh the snapshot
with `cd backend && APP_DATA_DIR=../data uv run python -m investwatch.registry.sync` (about 40 requests, 1 per second).

`data/golden/` (committed): the golden set for `make eval` and the calibration panel. Synthetic
pages and posts of fictional firms (`.example` domains), our `demo-sites/` pages, and labelled
real public posts referenced from `raw/posts.jsonl`. Every item records its provenance; items
scraped from social platforms are excluded from headline metrics. See `docs/eval/LABELING.md`.

`data/samples/` (git-ignored): the UKNF booth samples (pendrive). Put the files here as JSON,
JSONL or CSV (fields `url`, `text`, optional `platform`, `author`, `published_at`) and run the
`sample` source with target `samples`, or upload them with `POST /api/imports`
(`format=uknf_sample`). Ask UKNF before committing any of them.

`data/fixtures/synthetic/` (committed): synthetic records in the shape of the Meta Ad Library,
TikTok Commercial Content and YouTube Data APIs (`"synthetic": true`, fictional firms and people),
for demos without credentials. Never present them as collected data.
