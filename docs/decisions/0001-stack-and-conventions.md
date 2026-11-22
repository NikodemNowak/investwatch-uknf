# 0001: Stack and conventions

**Context:** 4 people (Nikodem, Bartosz, Mateusz, Jakub) working on two hackathon tasks in parallel, about 22 h, AI-assisted development; the jury values a working demo and a clean, reproducible process.

**Decision:** Python 3.12 + FastAPI + pydantic v2 backend (uv, ruff, mypy, pytest); React + Vite + strict TypeScript frontend (eslint, prettier); a separate `ai/` service and `demo-sites/`; Docker Compose for a one-command run; shared contributor rules for people and AI assistants.

**Consequences:** one set of commands (`make check`) for humans, agents and CI; contracts are explicit (`core/schemas.py` → OpenAPI → generated TS types).
