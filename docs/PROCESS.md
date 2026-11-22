# How InvestWatch was built: working with AI assistants

> Development happened in a private repository (39+ PRs, CI gate). This public repository is a single-commit snapshot for evaluation; PR numbers below refer to that history.

Numbers are as of `main` = `2931ec9` (PR #39, Sun 22.11), before the PR that refreshed this
file. They were re-stamped on Sun 22.11 with the commands in the last section; test counts come
from the last green CI run on `main` (run `44972226339`). PR #40 is open and its CI is blocked
by GitHub Actions billing, so it has no CI result.

## 1. Principle

The AI assistant writes the code, but it does not decide what is done. That is decided by the
rules in the repository, the plan with owners, the tests and CI. A human approves the direction,
the interface design and the legal constraints.

## 2. Fixed parts of the process

| Element | Where | What it enforces |
|---|---|---|
| One source of rules | A shared contributor rules file (kept in the development repository) | The same rules for people and every assistant (Claude Code, Codex, Cursor, Copilot): repo layout, style, commands, definition of done |
| Plan with owners | planning documents in the private repository (not included in this snapshot) | Tasks as packages with a file list, a verification command and an owner; an agent works only on its assigned package |
| Decisions | `docs/decisions/` (9 ADRs, 0001-0009) | Context, decision, consequences. ADR 0007 was explicitly superseded by 0008, so the change of mind stays in the repo; ADR 0009 records the fair-treatment policy for firms in the KNF registers |
| Contract before implementation | `backend/src/investwatch/core/schemas.py` + `data/fixtures/` (PR #2) | Backend, AI service and frontend were built in parallel on the same pydantic models and fixtures |
| Branch per task, PR, squash | `<login>/<topic>`, Conventional Commits, PR template (`.github/pull_request_template.md`) | A PR states what changed, which plan task, how it was verified, and contract or dependency changes |
| CI gate | `.github/workflows/ci.yml` | 9 jobs on every PR, 8 of them required. `main` is protected: the required jobs are `backend`, `frontend`, `ai`, `security` and `images` for each of the 4 images; the branch must be up to date with `main`, no force-push, and the rule applies to admins too. The ninth job, `e2e` (Playwright on the production build), runs on every PR but does not block |
| Same commands locally and in CI | `make check`, `make audit`, `make eval`, `make e2e-light` | Before a PR the agent runs what CI runs and pastes the result into the PR description |
| Tests first | Shared contributor rules | Logic starts from a test; every rule fix from error analysis has its own regression test (`ai/tests/test_rules_error_analysis.py`) |

## 3. Agents working in parallel

- Each agent gets its own `git worktree` and branch, so agents never overwrite each other's
  files. The plan gives the exact commands (`git worktree add ../iw-platform -b NikodemNowak/platform`).
- Merge order follows dependencies: the contract first (#2), then in parallel the AI service
  (#3), the frontend (#4) and the platform (#5).
- A change to the shared contract must show in the PR title (`feat(contract): ...`). Later
  examples: `Post.provenance` (#27), the hourly `TrendBucket` and `TrendPoint.bucket_at` (#28),
  and `GET /api/findings/{id}/review-queue` (#30), each with `frontend/src/api/types.ts` in the
  same PR.

## 4. Agent roles

| Role | Task | Trace in the repo |
|---|---|---|
| Implementation | One plan package in one worktree | PRs #2-#8, #10-#39 |
| Review by a stronger model | Assess the state against the jury criteria and the task spec, list gaps, prioritised backlog | review roadmap document in the private repository (#9): score 5.6/10 and a "done / partial / missing" table |
| Interface design | Design variants drawn on a canvas; a human picks and approves one before any code is written; the chosen variant is implemented and every screen is compared with it in screenshots | #6, #11, #18 ("approved C2 design") |
| Legal review | Research agents read the platforms' terms and API guides (YouTube Developer Policies, Meta Ad Library, TikTok Commercial Content API, Microsoft Ad Library) and list what is allowed; points they cannot settle are marked "to be confirmed" for UKNF's lawyer; a human takes the decision | ADR 0008, `docs/DATA_ACCESS.md`, `backend/tests/test_compliance.py` |
| Data | Legal sources only, provenance on every record | #17, #19, #27 (Microsoft Ad Library API, `make demo-real`), `docs/eval/DATA_SOURCES.md` |
| Evaluation | Golden set, `make eval`, ablation, bootstrap confidence intervals, before / after section | #16, #20, #28, `docs/eval/latest.md` |
| Labelling (agent consensus) | 3 independent reviewers (Claude Sonnet: lawyer, analyst, false-positive sceptic) without access to the proposed label or any model output; split votes adjudicated by Claude Opus | `docs/eval/LABELING.md`; 38 hold-out items, stored as `agent-consensus:3xsonnet+opus`, never as `human` |
| Training data | Synthetic texts: 234 generated by Claude Haiku, each checked blind by Haiku and Sonnet (`labeller: haiku-gen+haiku-blind+sonnet-blind-mixed`); 210 by gemma3:12b locally | `data/golden/synthetic/haiku_v1.jsonl`, `data/golden/augment/llm_train.jsonl`; used only by `make train`, never for metrics; listed in `docs/CREDITS.md` |
| Real-data review | Check whether findings about real, registered firms are fair after a `make demo-real` run | #28, ADR 0009, before / after table in `docs/eval/latest.md` |
| Jury rehearsal on a clean clone | Fresh `git clone`, README followed literally, own compose project, empty model volume, demo storyline walked in Chromium at 1440x900 | #29 (README and UI fixes), #30 (priority queue for checks, honest progress, submission form) |

## 5. Where a human decides

1. **Scope and division of work**: the plan and the package assignments.
2. **Interface design**: choosing and approving variant C2 on the design canvas before
   implementation (#18).
3. **Legal constraints**: the decision "official APIs and a crawler that identifies itself
   only" (ADR 0008). It removed working code (yt-dlp, parsing of platform pages) and 72 records
   from the golden set. `backend/tests/test_compliance.py` guards it.
4. **Fairness to registered firms**: a firm in the KNF registers is never labelled "no licence"
   or "high risk" on weak evidence (ADR 0009).
5. **Honest numbers**: metrics only from the hold-out split, nothing tuned on the hold-out,
   the dashboard's alert thresholds equal the evaluated ones (0.20 / 0.30 / 0.12, kept equal by
   `backend/tests/db/test_repo.py::test_default_thresholds_are_the_trained_ones`), and the agent
   review is called that in the report and in the UI.
6. **Merging**: a PR goes in after green CI.

## 6. Numbers

| Measure | Value |
|---|---|
| First commit to `966cf00` | 9 h 41 min (11:20-21:01); `main` has moved on to `2931ec9` (#39) since |
| Pull requests | 39 merged (squash, #2-#8 and #10-#39) at `2931ec9`; #40 open (CI blocked by GitHub Actions billing); 42 commits on `main`, only the first 3 (scaffold and plan) went to `main` directly |
| CI runs | counted at `966cf00`: 75 (42 on PRs, 33 on pushes to `main`), 74 green, 1 red on a PR branch; not re-counted since. On `main` the last run (#39) is green; one earlier push run (#37) was red and fixed by the next PR |
| CI jobs per PR | 9: `backend`, `ai`, `frontend`, `e2e`, `security`, `images` × 4 images; 8 required (all but `e2e`); about 2.5 min |
| Tests | backend 367 passed + 4 skipped, ai 206 passed (pytest), e2e 30 passed (Playwright) in 6 spec files, from the last green `main` CI log; frontend vitest 100, counted from source (`it(`/`test(` calls) because it is not in the log |
| Evaluation in CI | a stratified subset of the golden set in job `ai` on every PR |
| ADRs / plans | 9 / 3 |
| Scans | pip-audit, npm audit, gitleaks (full history + pre-commit), Trivy + CycloneDX SBOM for 4 images; results in [SECURITY.md](SECURITY.md) |

## 7. Limits of the process

- All PRs came from one account and GitHub has no recorded reviews. The controls were the CI
  gate, the verification notes in each PR, the whole-project review by a second model (#9) and
  the jury rehearsal on a clean clone (#29), not a line-by-line human review.
- The Playwright job `e2e` (production build, light stack) runs on every PR but is not required
  for merging.
- Plan checkboxes were not ticked as work progressed (2 of 48 in the 4-person plan); the list
  of PRs shows the actual state.
- No human has checked the hold-out labels.

## 8. How to check

```bash
gh pr list --state all --limit 100 --json state -q 'group_by(.state)|map({(.[0].state): length})'
gh run list --limit 300 --json conclusion -q 'group_by(.conclusion)|map({(.[0].conclusion): length})'
gh run list --limit 300 --json event -q 'group_by(.event)|map({(.[0].event): length})'
gh api repos/NikodemNowak/investwatch/branches/main/protection -q .required_status_checks.contexts
git rev-list --count origin/main                             # 42
ls docs/decisions | wc -l                                    # 9
(cd backend && uv run pytest --collect-only -q | tail -1)   # 367 + 4 skipped
(cd ai && uv run pytest --collect-only -q | tail -1)        # 206
(cd frontend && npx vitest list | wc -l)                     # 100
(cd frontend && npx playwright test --list | tail -1)        # 30 tests in 6 files
make check && make audit && make eval && make e2e-light
```
