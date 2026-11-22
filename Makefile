.PHONY: setup check backend-check ai-check frontend-check dev audit pip-audit npm-audit \
	golden eval eval-ci eval-compare train label public-data demo demo-real up-lite demo-lite \
	e2e e2e-light

setup:
	cd backend && uv sync
	cd ai && uv sync
	cd frontend && npm ci

backend-check:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q

ai-check:
	cd ai && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q

frontend-check:
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm run build

check: backend-check ai-check frontend-check

# Supply chain: known CVEs in the locked dependencies (the same steps run in CI job `security`).
PIP_AUDIT := uvx pip-audit@2.10.1 --require-hashes --disable-pip --progress-spinner off

pip-audit:
	@for svc in backend ai; do \
		echo "== pip-audit $$svc (uv.lock)"; \
		(cd $$svc && uv export --frozen --format requirements-txt --no-emit-project -q \
			| $(PIP_AUDIT) -r /dev/stdin) || exit 1; \
	done

npm-audit:
	@echo "== npm audit frontend (package-lock.json)"
	cd frontend && npm audit --audit-level=high

audit: pip-audit npm-audit

# Golden set (docs/eval/LABELING.md): rebuild items, evaluate, confirm labels.
golden:
	cd backend && uv run python -m investwatch.golden.build

# Full run through the real analysis: docs/eval/latest.md + data/golden/predictions.jsonl.
# MODE=rules|llm; EMBED=1 embeds items with bge-m3 (Ollama at OLLAMA_URL) like production.
MODE ?= rules
eval:
	cd ai && uv run python -m investwatch_ai.eval --mode $(MODE) $(if $(EMBED),--embed)

# M1 / M3 heads + thresholds from the TRAIN split (seeded; needs Ollama for the bge-m3 variant).
train:
	cd ai && uv run python -m investwatch_ai.classifier.train

# Before / after and ablation section of docs/eval/latest.md (needs Ollama; ~15 min with LLM).
# BASELINE_REF: a commit of this repository whose data/golden/predictions.jsonl is the "before" run
# (the public repository has one commit, so HEAD is only a placeholder; set it to a real older ref).
BASELINE_REF ?= HEAD
RUNS := ../data/golden/cache/runs
EVAL := uv run python -m investwatch_ai.eval --out /dev/null
eval-compare:
	mkdir -p data/golden/cache/runs
	git show $(BASELINE_REF):data/golden/predictions.jsonl > data/golden/cache/runs/before.jsonl
	cd ai && THRESHOLD_M2=0.6 $(EVAL) --no-classifier --predictions $(RUNS)/rules-old-thr.jsonl
	cd ai && $(EVAL) --no-classifier --predictions $(RUNS)/rules.jsonl
	cd ai && $(EVAL) --predictions $(RUNS)/lexicon.jsonl
	cd ai && uv run python -m investwatch_ai.classifier.train --no-extra --out $(RUNS)/w-golden
	cd ai && CLASSIFIER_DIR=$(RUNS)/w-golden $(EVAL) --embed --predictions $(RUNS)/golden-only.jsonl
	cd ai && $(EVAL) --embed --predictions $(RUNS)/embed.jsonl
	cd ai && $(EVAL) --embed --warning-list --predictions $(RUNS)/warning.jsonl
	cd ai && $(EVAL) --embed --mode llm --predictions $(RUNS)/llm.jsonl
	cd ai && uv run python -m investwatch_ai.eval --embed
	cd ai && uv run python -m investwatch_ai.eval.compare \
		--run "before: rules-v1, thr 0.5/0.6/0.5=$(RUNS)/before.jsonl" \
		--run "rules-v2, old thresholds=$(RUNS)/rules-old-thr.jsonl" \
		--run "rules-v2 + train thresholds=$(RUNS)/rules.jsonl" \
		--run "+ heads, lexicon fallback=$(RUNS)/lexicon.jsonl" \
		--run "+ heads bge-m3, golden-only training=$(RUNS)/golden-only.jsonl" \
		--run "+ heads bge-m3 (default)=$(RUNS)/embed.jsonl" \
		--run "+ LLM review=$(RUNS)/llm.jsonl" \
		--run "+ KNF warning list as a flag=$(RUNS)/warning.jsonl" \
		--notes ../docs/eval/notes.md

# Small stratified subset (what CI runs); the committed report is left alone.
eval-ci:
	cd ai && uv run python -m investwatch_ai.eval --subset ci --out ../data/eval-ci.md

# Public, legally sourced data (docs/eval/DATA_SOURCES.md): re-download the raw candidates
# (git-ignored, polite and slow: ~1 h for the Wayback part), then re-curate the committed files.
public-data:
	cd backend && uv run python -m investwatch.golden.sources.knf_warnings
	cd backend && uv run python -m investwatch.golden.sources.wayback --max-domains 160
	cd backend && uv run python -m investwatch.golden.sources.firm_pages
	cd backend && uv run python -m investwatch.golden.sources.curate knf_warnings_wayback
	cd backend && uv run python -m investwatch.golden.sources.curate firm_pages

label:
	cd backend && uv run python -m investwatch.golden.label --by "$(BY)"

# Demo state for the recording: start the stack, reset the database and replay the demo
# material through the real pipeline (crawl + render of demo-sites, file imports). Prints the
# counts per module and risk level. COMPOSE="docker compose -p x" to run a second copy.
# A stack that is already running is reused as is: the reset happens inside it, so an open
# dashboard never drops. REBUILD=1 rebuilds and recreates the containers first (after a pull).
COMPOSE ?= docker compose
define STACK_UP
	@if [ -z "$(REBUILD)" ] && [ -n "$$($(COMPOSE) ps --status running -q api 2>/dev/null)" ]; then \
		echo "stack already running: reusing it (REBUILD=1 to rebuild and recreate)"; \
	else $(COMPOSE) up -d --build; fi
	@echo "waiting for the API, the workers and demo-sites to be healthy..."
	@for svc in api worker-scrape worker-analyze demo-sites; do \
		until [ "$$($(COMPOSE) ps --format '{{.Health}}' $$svc)" = "healthy" ]; do sleep 3; done; \
	done
endef

demo:
	$(STACK_UP)
	$(COMPOSE) exec -T api python -m investwatch.demo

# Lite stack (docker-compose.lite.yml): rules + lexicon only, no Ollama and no model download.
# LITE_FILES can carry an extra local override (e.g. other host ports).
LITE_FILES ?= -f docker-compose.yml -f docker-compose.lite.yml
up-lite:
	$(COMPOSE) $(LITE_FILES) up --build

demo-lite:
	$(MAKE) demo COMPOSE="$(COMPOSE) $(LITE_FILES)"

# `make demo` plus real data fetched live and compliantly (data/seeds/real_demo.yaml):
# Microsoft Ad Library API + landing pages, KNF-registered firms' pages, live sites from the KNF
# warning list, YouTube Data API only with YOUTUBE_API_KEY. Slow on purpose (API spacing,
# Crawl-delay): ~20-40 min. Prints real and synthetic counts apart.
DEMO_TIMEOUT ?= 3600
demo-real:
	$(STACK_UP)
	$(COMPOSE) exec -T api python -m investwatch.demo --real --timeout $(DEMO_TIMEOUT)

# Browser tests of the production build (frontend/e2e). `make e2e`: against the full stack
# (`make demo` or `docker compose up` first; restarts `api` once). `make e2e-light`: the light
# stack CI runs (API on SQLite + mock AI, needs Redis at REDIS_URL).
E2E_BASE_URL ?= http://localhost:8080
e2e:
	cd frontend && E2E_BASE_URL=$(E2E_BASE_URL) \
		E2E_RESTART_API="$(COMPOSE) -f $(CURDIR)/docker-compose.yml restart api" npx playwright test

e2e-light:
	cd frontend && npm run build && bash e2e/light-stack.sh start && \
		{ E2E_RESTART_API="bash e2e/light-stack.sh restart-api" npx playwright test; \
		status=$$?; bash e2e/light-stack.sh stop; exit $$status; }
