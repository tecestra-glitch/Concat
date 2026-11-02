name: CI

on:
  push:
    branches: [main, 'claude/**']
  pull_request:
    branches: [main]

jobs:
  # ── Segurança ──────────────────────────────────────────────────
  security:
    name: TruffleHog Secret Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: TruffleHog
        uses: trufflesecurity/trufflehog@main
        with:
          extra_args: --only-verified

  # ── Frontend (se existir) ──────────────────────────────────────
  frontend:
    name: Frontend — lint + test + build
    runs-on: ubuntu-latest
    needs: security
    if: hashFiles('package.json') != ''
    defaults:
      run:
        working-directory: .  # altere se frontend estiver em subpasta
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: latest }
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm test --run
      - run: pnpm build

  # ── Backend Python (se existir) ────────────────────────────────
  backend:
    name: Backend — lint + test
    runs-on: ubuntu-latest
    needs: security
    if: hashFiles('pyproject.toml') != '' || hashFiles('backend/pyproject.toml') != ''
    defaults:
      run:
        working-directory: backend  # altere conforme estrutura
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -q

  # ── Docker (se existir) ───────────────────────────────────────
  docker:
    name: Docker build check
    runs-on: ubuntu-latest
    needs: [frontend, backend]
    if: hashFiles('Dockerfile') != '' || hashFiles('docker-compose.yml') != ''
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build --no-cache
        if: hashFiles('docker-compose.yml') != ''
      - run: docker build .
        if: hashFiles('Dockerfile') != '' && hashFiles('docker-compose.yml') == ''
