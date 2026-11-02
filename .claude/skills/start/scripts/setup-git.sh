#!/usr/bin/env bash
# setup-git.sh — configura git, husky e TruffleHog num projeto novo
# Uso: ./setup-git.sh [project_name] [branch_name]

set -euo pipefail

PROJECT="${1:-$(basename "$PWD")}"
BRANCH="${2:-main}"

echo "🔧 Configurando git para: $PROJECT (branch: $BRANCH)"

# ── Git init ──────────────────────────────────────────────────────────
if [ ! -d ".git" ]; then
  git init
  git checkout -b "$BRANCH" 2>/dev/null || true
  echo "✅ git init"
else
  echo "ℹ️  git já inicializado"
fi

# ── .gitignore base ───────────────────────────────────────────────────
if [ ! -f ".gitignore" ]; then
  cat > .gitignore << 'GITIGNORE'
# Desenvolvimento local (sempre ignorado)
/dev/
/design-system/
*.local

# Dependências
node_modules/
.pnpm-store/
__pycache__/
*.py[cod]
.venv/
.uv/

# Build
dist/
build/
.next/
out/
*.egg-info/

# Env
.env
.env.local
.env.*.local
!.env.example

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Testes
coverage/
.coverage
.pytest_cache/
test-results/
playwright-report/

# Docker
.docker/
GITIGNORE
  echo "✅ .gitignore criado"
fi

# ── Husky + TruffleHog (se package.json existir) ──────────────────────
if [ -f "package.json" ]; then
  # Instalar husky se não instalado
  if ! grep -q '"husky"' package.json 2>/dev/null; then
    pnpm add -D husky 2>/dev/null || npm install --save-dev husky 2>/dev/null || true
  fi

  # Inicializar husky
  pnpm exec husky init 2>/dev/null || npx husky init 2>/dev/null || mkdir -p .husky

  # pre-commit
  cat > .husky/pre-commit << 'HOOK'
#!/bin/sh
set -e
# TruffleHog — bloqueia só em segredos verificados (exit 183)
if command -v trufflehog >/dev/null 2>&1; then
  trufflehog git file://. --since-commit HEAD --only-verified --fail 2>/dev/null
  TH=$?
  if [ "$TH" -eq 183 ]; then
    echo "❌ TruffleHog: segredo detectado. Commit bloqueado."
    exit 1
  fi
elif docker info >/dev/null 2>&1; then
  docker run --rm -v "$(pwd):/pwd" trufflesecurity/trufflehog:latest \
    git file:///pwd --since-commit HEAD --only-verified --fail 2>/dev/null
  TH=$?
  if [ "$TH" -eq 183 ]; then
    echo "❌ TruffleHog: segredo detectado. Commit bloqueado."
    exit 1
  fi
else
  echo "⚠️  TruffleHog indisponível — varredura pulada"
fi
HOOK
  chmod +x .husky/pre-commit

  # pre-push
  cat > .husky/pre-push << 'HOOK'
#!/bin/sh
set -e
if command -v trufflehog >/dev/null 2>&1; then
  trufflehog git file://. --only-verified --fail 2>/dev/null
  TH=$?
  if [ "$TH" -eq 183 ]; then
    echo "❌ TruffleHog: segredo no histórico detectado. Push bloqueado."
    exit 1
  fi
fi
HOOK
  chmod +x .husky/pre-push

  echo "✅ Husky + TruffleHog configurados"
fi

# ── Pasta dev gitignored ──────────────────────────────────────────────
mkdir -p dev
if ! grep -q "^/dev/" .gitignore 2>/dev/null; then
  echo "/dev/" >> .gitignore
fi
echo "✅ ./dev/ criado e gitignored"

echo ""
echo "✅ Setup git concluído para $PROJECT"
