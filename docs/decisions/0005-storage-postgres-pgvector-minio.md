# 0005: Storage: Postgres + pgvector + MinIO

**Context:** We store structured findings, 1024-d embeddings for near-duplicate detection, and binary artefacts (HTML, screenshots, render snapshots, PDF reports).

**Decision:** Postgres 17 with pgvector (`pgvector/pgvector:pg17`) for metadata and vectors; MinIO (S3 API) for objects under `raw/`, `shots/`, `render/`, `media/`, `reports/`, served through presigned URLs.

**Consequences:** One database for SQL filters and cosine search (no separate vector DB); blobs stay out of Postgres; S3-compatible, so it can move to cloud storage unchanged.
