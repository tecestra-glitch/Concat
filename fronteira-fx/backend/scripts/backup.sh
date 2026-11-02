#!/usr/bin/env sh
# Dump the Postgres database (custom format, compressed). Works from the host against docker-compose.
# Usage: scripts/backup.sh [output_dir]   (env: PGSERVICE/DATABASE_URL or COMPOSE_SERVICE=postgres)
set -eu
OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT_DIR/fx-$STAMP.dump"
if [ -n "${DATABASE_URL:-}" ]; then
  # strip the SQLAlchemy driver suffix (postgresql+psycopg:// -> postgresql://)
  URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
  pg_dump --format=custom --compress=6 --no-owner --file="$FILE" "$URL"
else
  docker compose exec -T "${COMPOSE_SERVICE:-postgres}" pg_dump -U "${POSTGRES_USER:-fx}" --format=custom --compress=6 --no-owner "${POSTGRES_DB:-fx}" > "$FILE"
fi
echo "backup written: $FILE"
