#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?Set the TLS-enabled production PostgreSQL URL through a secret manager}"
: "${STORAGE_S3_BUCKET:?Set the private S3 bucket containing uploaded documents}"
: "${BACKUP_S3_URI:?Set a private S3 prefix such as s3://bucket/factorylink/postgres}"
: "${BACKUP_AGE_RECIPIENT:?Set the age public recipient key}"
: "${BACKUP_KMS_KEY_ID:?Set the AWS KMS key ID}"
: "${AWS_DEFAULT_REGION:?Set the AWS region}"

command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is required." >&2; exit 1; }
command -v age >/dev/null 2>&1 || { echo "age is required." >&2; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required." >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "tar is required." >&2; exit 1; }

[[ "$BACKUP_S3_URI" == s3://* && "$STORAGE_S3_BUCKET" != */* ]] || {
  echo "Use an S3 bucket name for STORAGE_S3_BUCKET and an s3:// URI for BACKUP_S3_URI." >&2
  exit 1
}
backup_bucket="${BACKUP_S3_URI#s3://}"
backup_bucket="${backup_bucket%%/*}"
[[ -n "$backup_bucket" && "$backup_bucket" != "$STORAGE_S3_BUCKET" ]] || {
  echo "The document source and encrypted backup must use separate S3 buckets." >&2
  exit 1
}

umask 077
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
object="factorylink-${stamp}.dump.age"
documents_object="factorylink-${stamp}-documents.tar.age"

pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" |
  age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" > "$tmp_dir/$object"
test -s "$tmp_dir/$object"
mkdir "$tmp_dir/documents"
aws s3 sync "s3://${STORAGE_S3_BUCKET%/}" "$tmp_dir/documents" --no-progress --only-show-errors
(cd "$tmp_dir" && find documents -type f -print0 | sort -z | xargs -0 -r sha256sum > DOCUMENTS.SHA256SUMS)
tar -C "$tmp_dir" -cf - documents DOCUMENTS.SHA256SUMS |
  age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" > "$tmp_dir/$documents_object"
test -s "$tmp_dir/$documents_object"
(
  cd "$tmp_dir"
  sha256sum "$object" "$documents_object" > SHA256SUMS
)

aws s3 cp "$tmp_dir/$object" "${BACKUP_S3_URI%/}/$object" \
  --sse aws:kms --sse-kms-key-id "$BACKUP_KMS_KEY_ID"
aws s3 cp "$tmp_dir/$documents_object" "${BACKUP_S3_URI%/}/$documents_object" \
  --sse aws:kms --sse-kms-key-id "$BACKUP_KMS_KEY_ID"
aws s3 cp "$tmp_dir/SHA256SUMS" "${BACKUP_S3_URI%/}/$object.SHA256SUMS" \
  --sse aws:kms --sse-kms-key-id "$BACKUP_KMS_KEY_ID"
printf 'Encrypted database and document backup uploaded: %s/%s and %s\n' \
  "${BACKUP_S3_URI%/}" "$object" "$documents_object"
