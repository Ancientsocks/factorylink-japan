#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=factorylink}"
: "${PGUSER:=factorylink}"
: "${PGPASSWORD:?Set PGPASSWORD for the PostgreSQL owner account}"
: "${RUNTIME_DB_USER:=factorylink_app}"
: "${RUNTIME_DB_PASSWORD:?Set RUNTIME_DB_PASSWORD for the restricted API role}"

PSQL=(psql -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE")
printf 'Waiting for PostgreSQL at %s:%s/%s ...\n' "$PGHOST" "$PGPORT" "$PGDATABASE"
PG_READY=false
for _ in $(seq 1 45); do
  if PGPASSWORD="$PGPASSWORD" "${PSQL[@]}" -c 'SELECT 1' >/dev/null 2>&1; then PG_READY=true; break; fi
  sleep 1
done
if [[ "$PG_READY" != true ]]; then echo "PostgreSQL did not become ready" >&2; exit 1; fi
bootstrap_runtime_role() {
  PGPASSWORD="$PGPASSWORD" "${PSQL[@]}" \
    -v runtime_db_user="$RUNTIME_DB_USER" \
    -v runtime_db_password="$RUNTIME_DB_PASSWORD" \
    -v postgres_owner="$PGUSER" \
    -f "$ROOT/scripts/db/create-runtime-role.sql"
}

export DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
MIGRATION_DATABASE_URL="$DATABASE_URL"
export RUNTIME_DB_USER

printf '\n[1/8] Create or refresh the least-privilege runtime role\n'
bootstrap_runtime_role

printf '\n[2/8] Apply all Alembic migrations as the schema owner\n'
(cd "$ROOT/backend" && python -m alembic upgrade head)

printf '\n[3/8] Seed fictional demo workspaces and records\n'
(cd "$ROOT/backend" && python -m app.seed)

printf '\n[4/8] Re-run role bootstrap to verify restart-safe grants\n'
bootstrap_runtime_role

printf '\n[5/8] Verify role attributes and column-level privileges\n'
PGPASSWORD="$PGPASSWORD" "${PSQL[@]}" \
  -v runtime_db_user="$RUNTIME_DB_USER" \
  -f "$ROOT/scripts/db/verify-runtime-role.sql"

printf '\n[6/8] Verify RLS isolation and supplier visibility/denials\n'
PGPASSWORD="$PGPASSWORD" "${PSQL[@]}" \
  -v runtime_db_user="$RUNTIME_DB_USER" \
  -f "$ROOT/scripts/db/verify-rls.sql"

printf '\n[7/8] Start API with runtime credentials and test real PostgreSQL workflow reads/writes\n'
export DATABASE_URL="postgresql+psycopg://${RUNTIME_DB_USER}:${RUNTIME_DB_PASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"
export ENVIRONMENT=development
export JWT_SECRET_KEY="factorylink-postgres-ci-smoke-secret-2026-do-not-use-in-production"
export AUTO_CREATE_SCHEMA=false
export SEED_DEMO_DATA=false
export ALLOW_PUBLIC_REGISTRATION=false
export EXPOSE_AUTH_ACTION_LINKS=false
export CORS_ORIGINS="http://127.0.0.1:5173"
export UPLOAD_DIR="${TMPDIR:-/tmp}/factorylink-postgres-acceptance-uploads"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
mkdir -p "$UPLOAD_DIR"
LOG_FILE="${TMPDIR:-/tmp}/factorylink-postgres-api.log"
WORKER_LOG="${TMPDIR:-/tmp}/factorylink-postgres-worker.log"
API_PID=""
WORKER_PID=""
cleanup() {
  if [[ -n "$API_PID" ]]; then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi
  if [[ -n "$WORKER_PID" ]]; then kill "$WORKER_PID" 2>/dev/null || true; wait "$WORKER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
(
  cd "$ROOT/backend"
  exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8127
) >"$LOG_FILE" 2>&1 &
API_PID=$!
FACTORYLINK_BASE_URL=http://127.0.0.1:8127 python "$ROOT/scripts/db/postgres-api-smoke.py" || {
  cat "$LOG_FILE" >&2 || true
  exit 1
}

printf '\n[8/8] Start restricted-role Celery worker and execute a tenant-aware task through Redis\n'
(
  cd "$ROOT/backend"
  exec celery -A app.celery_app.celery_app worker --loglevel=WARNING --pool=solo --concurrency=1
) >"$WORKER_LOG" 2>&1 &
WORKER_PID=$!
(cd "$ROOT/backend" && PYTHONPATH="$ROOT/backend" python "$ROOT/scripts/db/celery-smoke.py") || {
  cat "$WORKER_LOG" >&2 || true
  cat "$LOG_FILE" >&2 || true
  exit 1
}

printf '\n[9/10] Verify live Redis rate-limit enforcement, isolation and expiry\n'
PYTHONPATH="$ROOT/backend" python "$ROOT/scripts/db/redis-rate-limit-smoke.py"

printf '\n[10/10] Verify clean, predecessor, failed and recovered migrations in disposable databases\n'
export DATABASE_URL="$MIGRATION_DATABASE_URL"
python "$ROOT/scripts/db/migration-safety.py"

printf '\nPostgreSQL, API, Redis rate limiting, Celery and migration-safety acceptance completed successfully.\n'
