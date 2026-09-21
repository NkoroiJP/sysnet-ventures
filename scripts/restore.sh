#!/usr/bin/env bash
# Restore the Sysnet platform from a backup created by backup.sh.
# Usage: ./scripts/restore.sh db-<stamp>.dump media-<stamp>.tar.gz
set -euo pipefail

DB_FILE="${1:?Usage: restore.sh db-<stamp>.dump [media-<stamp>.tar.gz]}"
MEDIA_FILE="${2:-}"

echo "==> Restoring PostgreSQL from $DB_FILE..."
docker compose exec -T db pg_restore --clean --if-exists -U sysnet -d sysnet < "$DB_FILE"

if [ -n "$MEDIA_FILE" ]; then
  echo "==> Restoring media from $MEDIA_FILE..."
  docker compose exec -T web tar xz -C /app < "$MEDIA_FILE"
fi

echo "==> Running migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo "==> Restore complete."
