# Fronteira FX — API (FastAPI + alembic).
# Base pinada por digest. A versão do uv acompanha `uv_build` em pyproject.toml; para atualizar:
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:<versão>-python3.13-trixie-slim
FROM ghcr.io/astral-sh/uv:0.11.32-python3.13-trixie-slim@sha256:fb576a1ff0c6b967e8b466695af934e34161c4a99c2fbfb859261d4a24d4a8d3 AS base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependências primeiro (camada cacheável), projeto depois.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
# Base de conhecimento do RAG (knowledge/*.md), disponível em /app/knowledge para o seed.
COPY knowledge ./knowledge
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && python -m compileall -q /app/src

# Processo sem root, com UID/GID fixos (10001) iguais aos do worker: os dois montam o mesmo volume de
# evidências em /app/var/evidence e o dono do diretório tem de coincidir em qualquer ordem de arranque.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app/var/evidence \
    && chown -R app:app /app/var
USER app

EXPOSE 8000
# Mesmos tempos do healthcheck em docker-compose.yml (que o repete para ficar visível junto do depends_on).
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=12 \
    CMD ["/app/.venv/bin/python", "-c", "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/v1/health', timeout=4).status_code == 200 else 1)"]
# Migrações antes de servir; o worker do compose só sobe quando este container estiver saudável.
# `exec` deixa o uvicorn como PID 1 (recebe SIGTERM do `docker stop`).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn fronteira_fx.main:app --host 0.0.0.0 --port 8000"]
