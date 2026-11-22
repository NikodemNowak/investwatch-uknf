# Credits and licences

Every external model, dataset, service and library the product uses (hackathon rule: external
resources must be cited). Add a row in the same PR that introduces one. Prefer MIT / BSD /
Apache-2.0; rows in **bold** are the exceptions worth knowing about.

| Component | License | Used for |
|---|---|---|
| FastAPI, pydantic, uvicorn | MIT / MIT / BSD-3 | API servers (backend and `ai`) |
| React, Vite, Vitest | MIT | UI, build, unit tests |
| httpx, pydantic-settings | BSD-3 / MIT | HTTP client, config (backend and `ai`) |
| NumPy, scikit-learn | BSD-3 | `ai` embeddings math; M1 / M3 logistic-regression heads (`make train`, weights as JSON in `ai/src/investwatch_ai/classifier/weights/`) |
| RapidFuzz | MIT | `ai` fuzzy quote verification; backend fuzzy firm-name matching |
| KNF registers (knf.gov.pl, public register data) | public sector information; cite source and snapshot date (in the file and `GET /api/firms/status`) | `data/registry/` firm snapshot |
| PyYAML | MIT | `ai` rule metadata and Polish lexicon; backend seed sources |
| Ollama (runtime, not bundled) | MIT | local LLM / embedding server called by `ai` |
| bge-m3 (`BAAI/bge-m3`, via Ollama) | MIT | `ai` text embeddings |
| Gemma 4 (`gemma4:e2b-it-qat`, default `LLM_MODEL`, via Ollama) | Apache-2.0 ([Gemma 4 model card](https://gemma.ai/models/gemma-4/model-card/)) | `ai` LLM rule review (`llm` queue, CPU) |
| Gemma 3 (`gemma3:12b`, `GPU_LLM_MODEL`, via Ollama) | Gemma Terms of Use (free, not OSI) | LLM rule review on GPU |
| Gemma 3 (`gemma3:12b`, via Ollama), generated texts | Gemma Terms of Use (free, not OSI); outputs are ours | train-only synthetic texts `data/golden/augment/llm_train.jsonl` (`generator:llm`, never evaluated) |
| Claude Haiku / Sonnet (Anthropic), generated and cross-checked texts | Anthropic usage policies; outputs are ours | train-only synthetic texts `data/golden/synthetic/haiku_v1.jsonl` (`generator:haiku`, never evaluated) |
| TanStack Query | MIT | server state, caching |
| Recharts 3.10.1 | MIT | trend chart on "Do przejrzenia" (lazy-loaded) |
| Inter (`@fontsource-variable/inter`, Rasmus Andersson) | SIL OFL 1.1 (font), MIT (package) | UI typeface, self-hosted (latin + latin-ext) |
| socket.io-client | MIT | live alerts and job progress |
| React Router | MIT | routing |
| SQLAlchemy, Alembic | MIT | backend ORM and migrations |
| psycopg 3 | **LGPL-3.0** (dynamically linked, unmodified) | Postgres driver |
| pgvector (Python) / `pgvector/pgvector` image | MIT / PostgreSQL License | vector column, near-duplicate search |
| Celery, redis-py | BSD-3 / MIT | job queue, scheduler (Beat) |
| python-socketio | MIT | real-time alerts (`AsyncRedisManager`) |
| minio (Python SDK) | Apache-2.0 | object storage client |
| tldextract, croniter | BSD-3 / MIT | registrable domains for rate limits, per-source cron |
| Playwright (Python + `mcr.microsoft.com/playwright/python` image) | Apache-2.0 | backend base image; headless Chromium page render and screenshots |
| Valkey (`valkey/valkey` image) | BSD-3 | Celery broker + Socket.IO bus |
| MinIO server (`cgr.dev/chainguard/minio` image) | **AGPL-3.0** (unmodified, separate service) | S3 object storage |
| nginx | BSD-2 | demo-sites, frontend |
| YouTube Data API v3 | service, YouTube API Services Terms of Service | `youtube` collector |
| Meta Ad Library API | service, Meta Platform Terms | `meta_ad_library` collector |
| Microsoft Ad Library API (Microsoft Advertising) | public service, no key; [Microsoft Terms of Use](https://www.microsoft.com/en-us/legal/terms-of-use), [API guide](https://learn.microsoft.com/en-us/advertising/guides/ad-library-api?view=bingads-13) | `microsoft_ad_library` collector; recorded answers in `backend/tests/collectors/fixtures/microsoft_ad_library/` |
| TikTok Commercial Content API | service, TikTok for Developers Terms | `tiktok` collector |
| Common Crawl index | Common Crawl Terms of Use | optional URL discovery for `site` |
| GDELT DOC 2.0 API | free, citation required ("GDELT Project", gdeltproject.org) | optional news discovery for `site` |
| python-multipart | Apache-2.0 | file uploads (`POST /api/imports`, `/api/submissions`) |
| pip-audit, gitleaks, Trivy (CI and dev tools, not shipped) | Apache-2.0 / MIT / Apache-2.0 | dependency CVE scan, secret scan, image scan + SBOM |

Notes:
- Gemma 4 is released under Apache-2.0; Gemma 3 (GPU model and train-only text generation) is
  under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms), a custom licence that is
  free to use but not OSI-approved.
- psycopg 3 (LGPL-3.0) is used unmodified as a dynamically loaded library; MinIO (AGPL-3.0) runs
  unmodified as a separate service and is not linked into our code.
- Synthetic texts generated with Claude and Gemma 3 are used for training only and never for
  any reported metric ([eval/LABELING.md](eval/LABELING.md)).
