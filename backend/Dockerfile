# One image for api, workers, beat and seed (different commands in docker-compose.yml).
# The Playwright base ships Chromium + system deps; its tag must match `playwright` in pyproject.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# pwuser is the unprivileged user that comes with the Playwright image.
USER pwuser
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"
CMD ["uvicorn", "investwatch.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
