#!/usr/bin/env bash
# Instala o coletor ao vivo numa VM Ubuntu 24.04 (Oracle Cloud Always Free). O cloud-init roda este arquivo como root,
# depois de gravar /etc/fronteira-fx/worker.env e clonar o repositório em /opt/fronteira-fx. Pode rodar de novo sem estrago.
set -euo pipefail
REPO_DIR=/opt/fronteira-fx
ENV_FILE=/etc/fronteira-fx/worker.env
HERE="$REPO_DIR/fronteira-fx/deploy/oracle"
log() { echo "[fronteira-fx] $*"; }

[ -f "$ENV_FILE" ] || { log "falta $ENV_FILE"; exit 1; }
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

export DEBIAN_FRONTEND=noninteractive
# Máquina que já tem Docker (outro projeto): usa o que existe, não troca pacote nem reinicia nada.
if command -v docker >/dev/null 2>&1; then
  log "docker já instalado: mantendo"
  if ! docker compose version >/dev/null 2>&1; then
    log "instalando só o plugin compose"
    apt-get update -q
    apt-get install -y -q docker-compose-v2 || apt-get install -y -q docker-compose-plugin
  fi
  command -v git >/dev/null 2>&1 || { apt-get update -q; apt-get install -y -q git; }
else
  log "instalando docker e git"
  apt-get update -q
  apt-get install -y -q docker.io docker-compose-v2 git unattended-upgrades
  systemctl enable --now docker
fi

# A forma E2.1.Micro tem 1 GB: o Chromium precisa de folga.
mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
if [ "$mem_kb" -lt 3000000 ] && ! swapon --show | grep -q /swapfile; then
  log "criando 2 GB de swap"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "agendando a atualização automática (a cada 5 min)"
install -m 0644 "$HERE/fronteira-fx-update.service" /etc/systemd/system/fronteira-fx-update.service
install -m 0644 "$HERE/fronteira-fx-update.timer" /etc/systemd/system/fronteira-fx-update.timer
systemctl daemon-reload
systemctl enable --now fronteira-fx-update.timer

log "primeira subida do worker"
bash "$HERE/update.sh" --force
