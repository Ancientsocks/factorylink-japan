#!/usr/bin/env bash
set -euo pipefail

: "${RESTORE_DRILL_DATABASE_URL:?Set a TLS-enabled URL to a newly created, isolated scratch database}"
: "${RESTORE_DRILL_CONFIRM:?Set RESTORE_DRILL_CONFIRM=RESTORE_TO_SCRATCH_ONLY after verifying the target}"
: "${BACKUP_OBJECT_URI:?Set the encrypted backup S3 object URI}"
: "${RESTORE_DRILL_DOCUMENT_DIR:?Set an empty, isolated document directory ending in _restore_drill}"
: "${AGE_IDENTITY_FILE:?Set the path to the age private identity file}"

[[ "$RESTORE_DRILL_CONFIRM" == "RESTORE_TO_SCRATCH_ONLY" ]] || {
  echo "Refusing to restore without explicit scratch-database confirmation." >&2
  exit 1
}
command -v psql >/dev/null 2>&1 || { echo "psql is required." >&2; exit 1; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is required." >&2; exit 1; }
command -v age >/dev/null 2>&1 || { echo "age is required." >&2; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required." >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "tar is required." >&2; exit 1; }
[[ -r "$AGE_IDENTITY_FILE" ]] || { echo "The age identity file is not readable." >&2; exit 1; }

umask 077
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
object_name="${BACKUP_OBJECT_URI##*/}"
[[ "$object_name" == *.dump.age ]] || {
  echo "BACKUP_OBJECT_URI must identify an encrypted .dump.age object." >&2
  exit 1
}
encrypted="$tmp_dir/$object_name"
documents_name="${object_name%.dump.age}-documents.tar.age"
documents_encrypted="$tmp_dir/$documents_name"
dump="$tmp_dir/backup.dump"
manifest="$tmp_dir/SHA256SUMS"

aws s3 cp "$BACKUP_OBJECT_URI" "$encrypted"
aws s3 cp "${BACKUP_OBJECT_URI%/*}/$documents_name" "$documents_encrypted"
aws s3 cp "${BACKUP_OBJECT_URI}.SHA256SUMS" "$manifest"
(cd "$tmp_dir" && sha256sum --check SHA256SUMS)
age --decrypt --identity "$AGE_IDENTITY_FILE" --output "$dump" "$encrypted"
pg_restore --list "$dump" >/dev/null
age --decrypt --identity "$AGE_IDENTITY_FILE" --output "$tmp_dir/documents.tar" "$documents_encrypted"
mkdir "$tmp_dir/restored-documents"
if tar -tf "$tmp_dir/documents.tar" | awk '/^\// || /(^|\/)\.\.($|\/)/ { exit 1 }'; then
  tar -xf "$tmp_dir/documents.tar" -C "$tmp_dir/restored-documents"
else
  echo "Document archive contains an unsafe path; refusing to extract it." >&2
  exit 1
fi
if [[ -s "$tmp_dir/restored-documents/DOCUMENTS.SHA256SUMS" ]]; then
  (cd "$tmp_dir/restored-documents" && sha256sum --check DOCUMENTS.SHA256SUMS)
fi

[[ ! -L "$RESTORE_DRILL_DOCUMENT_DIR" ]] || {
  echo "Document restore target must not be a symbolic link." >&2
  exit 1
}
mkdir -p -- "$RESTORE_DRILL_DOCUMENT_DIR"
document_target="$(realpath -- "$RESTORE_DRILL_DOCUMENT_DIR")"
[[ "$document_target" == *_restore_drill ]] || {
  echo "Document restore target must end with _restore_drill; refusing to continue." >&2
  exit 1
}
[[ -z "$(find "$document_target" -mindepth 1 -print -quit)" ]] || {
  echo "Document restore target is not empty; refusing to replace its contents." >&2
  exit 1
}

target_database="$(
  psql --set=ON_ERROR_STOP=1 --tuples-only --no-align "$RESTORE_DRILL_DATABASE_URL" \
    --command="SELECT current_database();"
)"
[[ "$target_database" == *_restore_drill ]] || {
  echo "Restore target database name must end with _restore_drill; refusing to continue." >&2
  exit 1
}
existing_objects="$(
  psql --set=ON_ERROR_STOP=1 --tuples-only --no-align "$RESTORE_DRILL_DATABASE_URL" \
    --command="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f');"
)"
[[ "$existing_objects" == "0" ]] || {
  echo "Restore target is not empty; refusing to replace its objects." >&2
  exit 1
}

pg_restore --single-transaction --exit-on-error --no-owner --no-acl \
  --dbname="$RESTORE_DRILL_DATABASE_URL" "$dump"
cp -a -- "$tmp_dir/restored-documents/documents/." "$document_target/"
psql --set=ON_ERROR_STOP=1 --tuples-only --no-align "$RESTORE_DRILL_DATABASE_URL" \
  --command="SELECT version_num FROM alembic_version;"
echo "Database and document restore drill completed in isolated scratch targets. Run the staging smoke suite before cleanup."
