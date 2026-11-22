FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 app
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    AI_MODE=rules
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8001/health', timeout=4)"]
CMD ["uvicorn", "investwatch_ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
