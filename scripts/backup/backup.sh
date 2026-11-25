#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

command -v docker >/dev/null 2>&1 || { echo "Docker CLI is required for a Compose backup." >&2; exit 1; }
[[ -f .env ]] || { echo "Missing .env. Copy .env.example to .env first." >&2; exit 1; }

umask 077
BACKUP_ROOT="${BACKUP_DIR:-$ROOT/.backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && (( RETENTION_DAYS >= 1 )) || { echo "BACKUP_RETENTION_DAYS must be a positive integer." >&2; exit 1; }
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/factorylink-$STAMP"
TMP="$TARGET.tmp"
mkdir -p "$BACKUP_ROOT"; chmod 700 "$BACKUP_ROOT"; mkdir "$TMP"
trap 'rm -rf "$TMP"' ERR INT TERM

docker compose exec -T db sh -ec 'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/factorylink-backup.dump'
docker compose cp db:/tmp/factorylink-backup.dump "$TMP/database.dump"
docker compose exec -T db rm -f /tmp/factorylink-backup.dump

docker compose exec -T backend sh -ec 'tar -C /app/data -czf /tmp/factorylink-uploads.tar.gz uploads'
docker compose cp backend:/tmp/factorylink-uploads.tar.gz "$TMP/uploads.tar.gz"
docker compose exec -T backend rm -f /tmp/factorylink-uploads.tar.gz

[[ -s "$TMP/database.dump" && -s "$TMP/uploads.tar.gz" ]] || { echo "Backup output is empty." >&2; exit 1; }
(
  cd "$TMP"
  sha256sum database.dump uploads.tar.gz > SHA256SUMS
  printf 'created_at_utc=%s\nformat=PostgreSQL custom dump + uploads tar.gz\n' "$STAMP" > BACKUP_INFO.txt
)
mv "$TMP" "$TARGET"; chmod -R go-rwx "$TARGET"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'factorylink-*' -mtime "+$RETENTION_DAYS" -exec rm -rf -- {} +
echo "Backup created: $TARGET"
echo "Verify with: (cd '$TARGET' && sha256sum -c SHA256SUMS)"
