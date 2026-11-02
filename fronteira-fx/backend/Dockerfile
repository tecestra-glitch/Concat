# Fronteira FX API
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
RUN mkdir -p /app/var
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["uv", "run", "python", "-c", "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/v1/health', timeout=4).status_code==200 else 1)"]
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn fronteira_fx.main:app --host 0.0.0.0 --port 8000"]
