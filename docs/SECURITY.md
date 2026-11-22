# Security

## Controls
- Secrets live only in `.env` (git-ignored). Compose refuses to start without `POSTGRES_PASSWORD`
  and `MINIO_ROOT_PASSWORD`; change both before exposing the stack beyond localhost.
- Only the dashboard (8080) and the API (8000) are published; every other service is internal.
- "Check URL" fetches private hosts only from `CHECK_ALLOWED_INTERNAL_HOSTS` (SSRF guard).
- Third-party images are pinned (MinIO by digest); scanners in CI run from digest-pinned images.
- The pre-commit hook runs gitleaks.
- The app has no user authentication; expose it only behind a gate (reverse-proxy basic auth, VPN), as in the hosted demo.

Known limitation: the SSRF guard resolves the host name and checks the address before fetching, so a DNS-rebinding race (TOCTOU: the name resolves differently at fetch time) is not closed. Mitigation today: run the stack without access to internal networks beyond what `CHECK_ALLOWED_INTERNAL_HOSTS` lists.

## Scans
`make audit` runs `pip-audit` (backend and `ai`, on `uv.lock`, hashes required) and `npm audit`.
CI runs on every PR:

| Job | What | Blocks the PR on |
|---|---|---|
| `security` | gitleaks over the full git history; pip-audit; npm audit (runtime and all deps) | any leak, any known CVE in Python deps, high+ in npm |
| `images` (backend, ai, frontend, demo-sites) | Trivy CVE report (medium+) and a CycloneDX SBOM artifact per image | a critical CVE with a fix available |

## Results, 2026-11-21 (`main` = `966cf00`)
The figures below are as of `966cf00`. The fixes merged since (#31-#39) touched no dependencies (no change to `uv.lock`, `package-lock.json` or the manifests), so the dependency scans are unaffected; the image scan and gitleaks counts were not re-run.

Re-run on 2026-11-21 at about 21:15 CET with the same tool versions as CI (Trivy 0.69.3
`--ignore-unfixed`, gitleaks 8.30.1). The four project images were scanned by CI on the push of
`966cf00` to `main` (run `44944061057`, job "Trivy report"), because the images need a Docker
build; everything else was run locally on the same commit.

| Scan | Command | Result |
|---|---|---|
| pip-audit backend, ai | `make pip-audit` | 0 known vulnerabilities |
| npm audit, runtime deps | `cd frontend && npm audit --omit=dev --audit-level=high` | 0 |
| npm audit, all deps | `make npm-audit` | 0 |
| gitleaks, history of `main` | `gitleaks git --redact --log-opts=HEAD .` | 33 commits, no leaks |
| gitleaks, every branch in the local clone | `gitleaks git --redact .` (the command the CI job runs) | 159 commits, no leaks |
| Trivy backend | CI `images (backend)` | 0 critical, 1 high, 11 medium |
| Trivy ai | CI `images (ai)` | 0 critical, 1 high, 32 medium |
| Trivy frontend (`nginx:1.30-alpine`) | CI `images (frontend)` | 0 critical, 1 high, 7 medium |
| Trivy demo-sites | CI `images (demo-sites)` | 0 critical, 1 high, 7 medium |
| Trivy MinIO (pinned digest) | `trivy image --image-src remote --ignore-unfixed <MINIO_IMAGE from docker-compose.yml>` | 0 |

The four high findings are all in base-image packages, not in our locked dependencies:
setuptools bundled with the Playwright base image (backend, CVE-2025-47273), zlib in Debian
(ai, CVE-2026-85091) and libxml2 in Alpine (frontend and demo-sites, CVE-2026-86144). Fixed
versions exist upstream and arrive with refreshed base images; CI reports them on every run.
Read the per-image counts again with
`gh run view 44944061057 --log | grep -E "Total: [0-9]+ \("`.
