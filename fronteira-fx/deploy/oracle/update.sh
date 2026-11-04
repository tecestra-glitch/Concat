#!/usr/bin/env bash
# Puxa a branch do projeto e, se mudou (ou com --force), reconstrói e reinicia o worker.
# Roda pelo timer fronteira-fx-update a cada 5 minutos. Quem pode enviar commits para a branch controla o que roda aqui.
set -euo pipefail
REPO_DIR=/opt/fronteira-fx
BRANCH="${FX_BRANCH:-claude/painel-cambio-apis-h2hj4d}"
cd "$REPO_DIR"
before=$(git rev-parse HEAD)
git fetch --quiet --depth 1 origin "$BRANCH"
after=$(git rev-parse FETCH_HEAD)
if [ "$before" = "$after" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi
git reset --quiet --hard FETCH_HEAD
cd "$REPO_DIR/fronteira-fx/deploy/oracle"
docker compose build --pull worker
docker compose up -d --remove-orphans worker
docker image prune -f >/dev/null
echo "[fronteira-fx] worker em $(git -C "$REPO_DIR" rev-parse --short HEAD)"
