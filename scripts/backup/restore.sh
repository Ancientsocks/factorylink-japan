#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
usage() { echo "Usage: $0 <backup-directory> --confirm" >&2; exit 2; }
[[ $# -eq 2 && "$2" == "--confirm" ]] || usage
BACKUP_PATH="$(cd "$1" 2>/dev/null && pwd)" || { echo "Backup directory not found." >&2; exit 1; }
for file in database.dump uploads.tar.gz SHA256SUMS; do [[ -s "$BACKUP_PATH/$file" ]] || { echo "Missing or empty $file." >&2; exit 1; }; done
(cd "$BACKUP_PATH" && sha256sum -c SHA256SUMS)
while IFS= read -r entry; do
  case "$entry" in
    /*|..|../*|*/../*|*/..) echo "Unsafe path in uploads archive: $entry" >&2; exit 1 ;;
    uploads|uploads/*) ;;
    *) echo "Unexpected path in uploads archive: $entry" >&2; exit 1 ;;
  esac
done < <(tar -tzf "$BACKUP_PATH/uploads.tar.gz")
cat <<'WARN'
WARNING: this replaces PostgreSQL data and the uploaded-document directory.
External traffic must be stopped. Pre-restore database and uploads copies will
be saved alongside the selected backup. A restore failure leaves app services
stopped for safe recovery.
WARN
read -r -p 'Type RESTORE to continue: ' answer
[[ "$answer" == "RESTORE" ]] || { echo "Restore cancelled."; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# Keep rollback copies of the current target before changing either data store.
docker compose exec -T db sh -ec 'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/factorylink-pre-restore.dump'
docker compose cp db:/tmp/factorylink-pre-restore.dump "$BACKUP_PATH/pre-restore-database-$STAMP.dump"
docker compose exec -T db rm -f /tmp/factorylink-pre-restore.dump
docker compose exec -T backend sh -ec 'tar -C /app/data -czf /tmp/factorylink-pre-restore-uploads.tar.gz uploads'
docker compose cp backend:/tmp/factorylink-pre-restore-uploads.tar.gz "$BACKUP_PATH/pre-restore-uploads-$STAMP.tar.gz"

# Stop user-facing/async work first. Keep backend alive only long enough to
# safely restore its mounted uploads volume, then stop it before DB replacement.
docker compose stop frontend worker scheduler

docker compose cp "$BACKUP_PATH/uploads.tar.gz" backend:/tmp/factorylink-restore-uploads.tar.gz
docker compose exec -T backend sh -ec '
  set -eu
  stage=/tmp/factorylink-restore-stage
  rollback=/tmp/factorylink-pre-restore-uploads.tar.gz
  rm -rf "$stage"; mkdir -p "$stage"
  tar -tzf /tmp/factorylink-restore-uploads.tar.gz | awk '\''BEGIN{bad=0} /^\// || /(^|\/)\.\.($|\/)/ {bad=1} !/^uploads($|\/)/ {bad=1} END{exit bad}'\''
  tar -xzf /tmp/factorylink-restore-uploads.tar.gz -C "$stage"
  test -d "$stage/uploads"
  find /app/data/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  if cp -a "$stage/uploads/." /app/data/uploads/; then
    rm -rf "$stage"
  else
    find /app/data/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar -xzf "$rollback" -C /app/data
    exit 1
  fi
  rm -f /tmp/factorylink-restore-uploads.tar.gz "$rollback"
'
docker compose stop backend

docker compose cp "$BACKUP_PATH/database.dump" db:/tmp/factorylink-restore.dump
docker compose exec -T db sh -ec 'pg_restore --single-transaction --exit-on-error --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/factorylink-restore.dump; rm -f /tmp/factorylink-restore.dump'

# pg_dump excludes ACLs by design; recreate the runtime role and reviewed
# column grants, then apply any migrations newer than the restored backup.
docker compose run --rm db-bootstrap
docker compose run --rm --no-deps -e SEED_DEMO_DATA=false migrate

docker compose up -d backend worker scheduler frontend
echo "Restore completed. Verify health, tenant access and document downloads before reopening external traffic."
echo "Rollback database: $BACKUP_PATH/pre-restore-database-$STAMP.dump"
echo "Rollback uploads:  $BACKUP_PATH/pre-restore-uploads-$STAMP.tar.gz"
