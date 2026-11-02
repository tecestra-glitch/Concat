#!/usr/bin/env sh
# Restore a dump produced by scripts/backup.sh. DESTROYS current data (--clean --if-exists).
# Usage: scripts/restore.sh backups/fx-YYYYmmddTHHMMSSZ.dump
set -eu
FILE="${1:?usage: restore.sh <dump file>}"
if [ -n "${DATABASE_URL:-}" ]; then
  URL="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+psycopg://#postgresql://#')"
  pg_restore --clean --if-exists --no-owner --dbname="$URL" "$FILE"
else
  docker compose exec -T "${COMPOSE_SERVICE:-postgres}" pg_restore -U "${POSTGRES_USER:-fx}" --clean --if-exists --no-owner --dbname="${POSTGRES_DB:-fx}" < "$FILE"
fi
echo "restored from: $FILE"
