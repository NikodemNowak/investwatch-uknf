# Operations

Run-time behaviour, measured timings and troubleshooting. Quick start: [README](../README.md).

## Development servers
```bash
make setup
cd backend && uv run uvicorn investwatch.main:app --reload    # :8000
cd frontend && npm run dev                                       # :5173, proxies /api
cd frontend && npm run dev:mock                                  # UI on fixtures, no backend
```
All commands: see the [Makefile](../Makefile) and the README sections Quick start and Testing.

## Measured timings
No GPU needed. Measured on 21.11 on a fresh `git clone` (i7-13700KF, 20 threads, 24 GB RAM,
no GPU, `docker compose up` without the GPU override; base images already in the local Docker
cache, own images built with `--no-cache`, empty `ollama` volume):

| Step | Time |
|---|---|
| `git clone` → dashboard (`:8080`) and API answer | **67 s** (clone + build 41 s, start 26 s) |
| … → LLM ready (`ollama-init` pulled bge-m3 1.2 GB + `gemma4:e2b-it-qat` 4.3 GB) | 227 s |
| `POST /api/check` `demo-sites/hidden-risk.html` → record + Socket.IO `alert` | **1.4-1.6 s** (5.1 s with `ollama` stopped) |
| … → model verdict (Socket.IO `finding_updated`, `llm_review=done`) | +13 s warm, +19 s on the first call (cold model load) |
| Model call per review on CPU (11 reviews: 580-2150 prompt / 90-490 output tokens) | 5.7-16.1 s, median 7.6 s |
| `ollama` stopped → finding marked `llm_review=unavailable` | +13.6 s after the alert; retried every 120 s (3x) |

On `hidden-risk.html` the rules give rule 9 `unknown`; the model settles it (`pass`), and on
`occluded-risk.html` / `tiny-font.html` likewise. On a machine without the base images add
their download (about 15 GB, see Memory and disk below). The dashboard works while the models download:
findings come from the rules with `llm_review=unavailable`, and the queued model reviews are
retried every 2 minutes until the model is there (seen at startup: the 6 findings analysed during the pull went
`unavailable` → `done` once the pull finished). Beat embeds seeded posts as soon as bge-m3 is
pulled (20/20 posts had a vector and a token count in the run above).

## Memory and disk
Measured RAM with both models loaded: Ollama 6.6 GB (gemma4:e2b 3.6 GB + bge-m3 1.2 GB
resident + runtime), all other services about 1.3 GB together. With `OLLAMA_NUM_PARALLEL=2`
(two requests per model, 21.11 evening) `ollama ps` shows gemma4:e2b 3.8 GB + bge-m3 1.2 GB and
the container used 4.5 GB during `make demo`; `worker-check` adds about 0.4 GB, so the other
services are about 2 GB. Set `OLLAMA_NUM_PARALLEL: "1"` in `docker-compose.yml` on an 8 GB machine. Disk: images `ollama/ollama`
8.5 GB, backend (Playwright + Chromium) 4.1 GB, `ai` 1.0 GB, `pgvector` 0.65 GB, the rest
< 0.5 GB; models 4.3 GB (`gemma4:e2b-it-qat`) + 1.2 GB (`bge-m3`) in the `ollama` volume.

## Troubleshooting
- `Invalid configuration: COLLECTOR_USER_AGENTS: ...` at startup: an old `.env` still has a browser-like User-Agent, which the compliant crawler refuses since #17.
  Fix: empty `COLLECTOR_USER_AGENTS` or copy its line from `.env.example` (`cp .env.example .env` for a demo).
- Models still downloading: the dashboard and alerts work; findings carry `llm_review=unavailable` and are reviewed once `ollama-init` finishes (`docker compose logs -f ollama-init`).
- Port 8080 or 8000 taken: stop the other process or change the `ports:` mapping in `docker-compose.yml`.
- `make demo` keeps printing `waiting: 0 sources, N posts` for minutes: the CPU is shared (another
  Ollama, a build). Embeddings and model reviews go through the one `ollama` service (two
  requests per model, `OLLAMA_NUM_PARALLEL=2`; embeddings wait up to `EMBED_TIMEOUT_S=45` s and a
  post that still gets none is embedded later by Beat's `embed_missing_posts`), so analysis
  waits for it; the command finishes on its own (it stops waiting after 900 s, `demo-real` after
  `DEMO_TIMEOUT`, default 3600 s). Measured with a second InvestWatch stack running on the same machine: 760 s
  instead of about 70 s.
- "Sprawdź" shows "Wynik wstępny (czeka na ocenę modelu)": the rules' problems are already
  shown, only the requirements left to the model wait. Analyst work never queues behind batch
  work: "Sprawdź" and "Zgłoś materiał" run their fetch, render and rules on `worker-check`
  (queue `check`) and their model review on `llm_priority`, which `worker-llm` always drains
  before the batch queue `llm` (`CELERY_QUEUE_ORDER=priority`). The progress card says where the
  review is: "Czeka w kolejce (N przed)" (N = reviews running or ahead in `llm_priority`), then
  "Czyta teraz". Measured during `make demo` (CPU, 23-30 demo reviews queued): rules after 5.2 s,
  model verdict after 32 s; the same review at the end of the batch queue would have waited
  about 6 min. `GET /api/findings/{id}/review-queue` returns the position.
- A finding page says "Zgłoszenie usunięte (np. po resecie demo)": the finding was deleted by
  `make demo` while open; the page stops asking for it.

## Demo data

`make demo` (any time, also on a running stack; `COMPOSE="docker compose -p name"` or
`COMPOSE_PROJECT_NAME=name` for a second copy: image names carry the project name, so copies never
overwrite each other's images) starts the stack if it is not running (a running stack is reused
without rebuilding or recreating containers, so an open dashboard keeps working; `REBUILD=1`
rebuilds first), empties every table, runs `seed` and replays the demo through the real
pipeline with `python -m investwatch.demo` in the `api` container:

- 15 enabled `demo-sites` sources run through `scrape_source` (polite fetch, Playwright render,
  analysis): compliant / non-compliant pairs, `ok.html` and `ok-maly-druk.html` with the same
  text and a different layout (two findings, different verdicts), and the TDM- and
  robots.txt-closed pages (status `blocked`). `hidden-risk.html` stays disabled for the live
  "Sprawdź" demo.
- the file-import connector (as `POST /api/imports`) loads 6 public pages of registered firms
  and 3 archived pages of entities on the KNF warning list (golden set, with provenance), and
  synthetic social items (`data/demo/social.jsonl`, `data/fixtures/synthetic/`, all marked
  `synthetic`, fictional firms and people); one ad appears on two platforms and forms one
  occurrence group.
- calibration uses the golden-set labels (`seed`); the model's second opinion keeps arriving
  after the command returns (about 20 reviews; wait a few minutes before recording a live
  "Sprawdź" if its model verdict should arrive in about 13 s).
- the curated live sources (`data/seeds/sources.yaml`, with `SEED_LIVE_SOURCES=true`) are added
  back after the reset, so "Monitoring" shows the platform APIs as "Wymaga klucza" /
  "Wymaga zgody platformy" with the steps to get access.

Measured on 21.11 (CPU, `AI_MODE=llm`): 41 posts, 50 findings (M1 7 high / 1 medium / 2 low,
M2 13 / 2 / 9, M3 12 / 1 / 3), 2 duplicates in occurrence groups, 6 findings flagged as KNF
warning-list publishers, 68 s. Then `make e2e` runs the browser tests against the stack
(`make e2e-light` is the CI variant: API on SQLite with the mock analyzer).
