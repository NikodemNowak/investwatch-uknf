# Architecture

Services, pipeline and APIs in more detail than the [README](../README.md). Decisions and their reasons: [decisions/](decisions/). API reference: http://localhost:8000/docs (OpenAPI).

## Services and pipeline
`docker compose up --build` starts: `frontend` (:8080), `api` (FastAPI + Socket.IO, :8000),
`worker-check` (analyst checks) / `worker-scrape` / `worker-analyze` / `worker-llm` (`llm_priority` before `llm`) / `beat` (Celery), `ai` (:8001, internal),
`ollama` + `ollama-init` (pulls `EMBED_MODEL` and `LLM_MODEL` in the background; nothing waits
for it), `postgres` (pgvector), `redis` (Valkey), `minio`, `seed` (migrations, KNF register snapshot, demo sources, golden labels; no findings) and `demo-sites` (fictional firm pages). Only 8080 and
8000 are published. `docker-compose.gpu.yml` adds the NVIDIA reservation and a 12B model.

- `AI_MODE=llm` (default): rules, render checks and the embedding run in the `analyze` queue
  and raise the alert in seconds; findings with rules the regex layer cannot settle (2, 3, 9,
  11, 12a, 15, 17, 18) are queued for `review_finding` on the `llm` queue (`worker-llm`,
  concurrency 1, 90 s hard limit per model call). The verdict updates the record (only quotes
  found verbatim in the text count), emits Socket.IO `finding_updated` and, if the score now
  crosses the threshold, a late `alert`. Each finding carries `llm_review`: `none` / `queued`
  / `done` / `unavailable`. `AI_MODE=rules` skips the model, `mock` skips `ai` entirely; if
  `ai` is unreachable the backend falls back to its keyword stand-in.
- Every analysed post stores its processing trace (characters, bge-m3 tokens, embedding size,
  per-stage timings, model, prompt/output tokens and time of the review), returned as
  `trace` with each finding. Beat backfills embeddings for posts that never went through the
  pipeline (e.g. imported before Ollama was up). CPU model: `gemma4:e2b-it-qat` (4.3 GB, the smallest Gemma 4 in the
  Ollama library) answers in 6-16 s; `gemma3:4b` needed 27 s for the same prompt on the same
  machine.
- Alert thresholds live in the `settings` table (`GET/PUT /api/settings/thresholds`) and are sent
  with every `POST ai:/analyze`.
- Try it: `curl -XPOST localhost:8000/api/check -H 'content-type: application/json'
  -d '{"url":"http://demo-sites/hidden-risk.html"}'` → Socket.IO `job` events and an `alert`.
- Visual audit: "check URL" and `web` sources render the page in headless Chromium (1440×900,
  820×1180, 390×844), store full-page screenshots and a `RenderSnapshot` (font, colours, bbox,
  visibility per text block) and the `ai` render rules 4-8 and 13 return evidence boxes for them
  (`GET /api/posts/{id}/screenshots/{viewport}`). `RENDER_ENABLED=false` falls back to HTTP text.
  `demo-sites/` has compliant / non-compliant page pairs; see its `index.html`.
- KNF register: the four investment-firm registers of attachment 1 (snapshot of 2026-11-21:
  28 domy maklerskie, 10 banks with brokerage, 10 EU branches, 709 EU firms without a branch =
  757 firms) are committed in `data/registry/knf_registry.json`; Beat re-fetches them daily
  (1 request/s) and falls back to the snapshot offline. `GET /api/firms?q=`, `/api/firms/{id}`,
  `/api/firms/status`, `POST /api/firms/sync`. Matching (domain, handle, legal name, trade and
  former names, RapidFuzz) decides author (→ M2) vs mention (→ M1) and the M3 gate.
- API docs: http://localhost:8000/docs. Socket.IO accepts origins listed in `CORS_ORIGINS`.

## Reports
`GET /api/reports/{m1|m2|m3}.csv` and `.json` export a module report with the same filters as
`GET /api/findings` (`status`, `platform`, `from`, `to`, `min_score`, `q`, ...). CSV is UTF-8 with
BOM; `?sep=;` gives semicolons and decimal commas for Excel in the Polish locale.
`GET /api/reports/{m1|m2|m3|all}.pdf` prints the same rows as an A4 landscape table, and
`GET /api/findings/{id}/report.pdf` gives the one-page evidence report of a finding (entity, KNF
status, problems with their legal basis, cropped screenshot with the measurements, URL, how it was
obtained, SHA-256 of the text and the screenshot, timestamps). Both are print HTML rendered by the
Chromium already in the backend image (`render/pdf.py`): offline, every request other than
`data:` URLs is aborted, so the report never fetches anything.

## Provenance and system status
- `GET /api/findings/{id}/trace` ("Pod maską" on the finding page): the source and its cron, the
  Celery task, queue and worker of the collect, analyze and llm stages, the crawler's User-Agent,
  egress proxy (credentials stripped), robots.txt verdict, HTTP status and timings (stored in
  `raw/<post>.json` as `fetch` and `job`), MinIO keys with size and SHA-256 (kept in object
  metadata), tokens, embedding, rules version, classifier head and its contribution, LLM model and
  tokens, per-step timings and the nearest posts by pgvector cosine.
- `GET /api/system` (Monitoring, "Stan systemu"): database, Redis, MinIO, workers per queue
  (`celery inspect`), Beat (last tick recorded in Redis by `tick_sources`), the `ai` service and
  Ollama models, and the next scheduled source run. Probes run in parallel with a 1.5 s timeout and
  the result is cached for 10 s.

## Filters and the result aggregator
`GET /api/findings` filters by period (`from`, `to`: whole UTC days, inclusive), source
(`platform`, `collector`), `risk_level`, `status` and `module`; `platform`, `risk_level` and
`status` repeat for several values (`status=new&status=in_review` is the open queue). The UI
("Do przejrzenia") keeps the filter bar in the URL (`okres`, `od`, `do`, `zrodlo`, `ryzyko`,
`status`), so a filtered view can be shared; the analyst changes a status straight from a row.

`GET /api/entities` is the result aggregator ("Agregator wyników"): the same filters pick the
findings, `entities/aggregate.py` groups them into one object per entity and `q` searches entity
names. A finding belongs to its matched firm (`firm:<uuid>`); an M1 ad also belongs to the third
party that ran it, and material without a firm belongs to its publisher (`name:<normalised
advertiser, author or domain>`), so an influencer's M1 ads and M3 advice end up on one card. Each
object carries counts per module, open / confirmed findings, the highest risk, occurrences,
platforms, first / last sighting, the KNF register state (`knf`, `fictional`, `absent`) and the
first KNF warning-list match. `GET /api/entities/{key}` is the drill-down with the findings,
newest first (the timeline). The mock UI mirrors the grouping in `frontend/src/lib/entities.ts`.
