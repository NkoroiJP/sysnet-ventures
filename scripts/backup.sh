#!/usr/bin/env bash
# (scripts receive executable bit in git; chmod +x scripts/*.sh after checkout)
# Backup the Sysnet platform: PostgreSQL dump + uploaded media.
# Usage: ./scripts/backup.sh [output_dir]
set -euo pipefail

OUT_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT_DIR"

echo "==> Backing up PostgreSQL..."
docker compose exec -T db pg_dump -U sysnet -d sysnet -Fc \
  > "$OUT_DIR/db-$STAMP.dump"

echo "==> Backing up media files..."
docker compose exec -T web tar cz -C /app media \
  > "$OUT_DIR/media-$STAMP.tar.gz"

echo "==> Done:"
ls -lh "$OUT_DIR" | tail -2
echo ""
echo "Restore with: ./scripts/restore.sh $OUT_DIR/db-$STAMP.dump $OUT_DIR/media-$STAMP.tar.gz"
