#!/usr/bin/env bash
# Instala o coletor ao vivo do Fronteira FX numa VM que já existe (Ubuntu), sem mexer no que já roda nela.
# Uso, dentro da VM:  curl -fsSL <este arquivo no GitHub> | sudo FX_DB_URL='postgresql+psycopg://...' bash
# FX_DB_URL é a conexão do papel fx_worker no Supabase (porta 5432). Nunca versione esse valor.
set -euo pipefail
BRANCH="${FX_BRANCH:-claude/painel-cambio-apis-h2hj4d}"
REPO_DIR=/opt/fronteira-fx
log() { echo "[fronteira-fx] $*"; }
[ "$(id -u)" = 0 ] || { log "rode com sudo"; exit 1; }
[ -n "${FX_DB_URL:-}" ] || { log "falta FX_DB_URL"; exit 1; }
case "$FX_DB_URL" in postgresql+psycopg://fx_worker.*) ;; *) log "FX_DB_URL não é do papel fx_worker"; exit 1;; esac

install -d -m 700 /etc/fronteira-fx
umask 077
cat > /etc/fronteira-fx/worker.env <<ENV
DATABASE_URL=${FX_DB_URL}
DATA_MODE=real
AUTO_CREATE_SCHEMA=0
SEED_KNOWLEDGE=0
SEED_DEMO=0
EVIDENCE_DIR=/app/var/evidence
WORKER_TICK_S=10
POLL_INTERVAL_S=60
WATCH_MAX_INTERVAL_S=180
ENV
chmod 600 /etc/fronteira-fx/worker.env
umask 022

command -v git >/dev/null 2>&1 || { apt-get update -q; apt-get install -y -q git; }
if [ ! -d "$REPO_DIR/.git" ]; then
  log "clonando a branch $BRANCH (só fronteira-fx/)"
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$BRANCH" https://github.com/tecestra-glitch/Concat "$REPO_DIR"
  git -C "$REPO_DIR" sparse-checkout set fronteira-fx
fi
bash "$REPO_DIR/fronteira-fx/deploy/oracle/setup.sh"
log "pronto: o coletor sobe em segundo plano; acompanhe com"
log "  sudo docker compose -f $REPO_DIR/fronteira-fx/deploy/oracle/compose.yml logs -f worker"
