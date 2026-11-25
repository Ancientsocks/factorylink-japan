param([Parameter(Mandatory=$true)][string]$BackupDirectory, [switch]$ConfirmRestore)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "../..")
if (-not $ConfirmRestore) { throw "Restore is destructive. Re-run with -ConfirmRestore after reviewing the backup." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI not found." }
$backup = (Resolve-Path $BackupDirectory).Path
foreach ($name in @("database.dump", "uploads.tar.gz", "SHA256SUMS")) { if (-not (Test-Path (Join-Path $backup $name))) { throw "Backup file missing: $name" } }
foreach ($line in Get-Content (Join-Path $backup "SHA256SUMS")) {
    $parts = $line -split '\s+', 2
    if ($parts.Count -ne 2) { throw "Invalid SHA256SUMS format." }
    $actual = (Get-FileHash (Join-Path $backup $parts[1].Trim()) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $parts[0].ToLowerInvariant()) { throw "Checksum mismatch: $($parts[1])" }
}
Write-Warning "This replaces the target database and uploads. Stop external traffic first. Pre-restore copies are saved alongside this backup."
if ((Read-Host "Type RESTORE to continue") -cne "RESTORE") { throw "Restore cancelled." }
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

# Keep rollback files before touching the target.
docker compose exec -T db sh -ec 'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/factorylink-pre-restore.dump'
if ($LASTEXITCODE -ne 0) { throw "Could not create pre-restore database dump." }
docker compose cp "db:/tmp/factorylink-pre-restore.dump" (Join-Path $backup "pre-restore-database-$stamp.dump")
if ($LASTEXITCODE -ne 0) { throw "Could not save pre-restore database dump." }
docker compose exec -T db rm -f /tmp/factorylink-pre-restore.dump | Out-Null
docker compose exec -T backend sh -ec 'tar -C /app/data -czf /tmp/factorylink-pre-restore-uploads.tar.gz uploads'
if ($LASTEXITCODE -ne 0) { throw "Could not create pre-restore uploads archive." }
docker compose cp "backend:/tmp/factorylink-pre-restore-uploads.tar.gz" (Join-Path $backup "pre-restore-uploads-$stamp.tar.gz")
if ($LASTEXITCODE -ne 0) { throw "Could not save pre-restore uploads archive." }

docker compose stop frontend worker scheduler
if ($LASTEXITCODE -ne 0) { throw "Could not stop frontend/worker/scheduler." }
docker compose cp (Join-Path $backup "uploads.tar.gz") "backend:/tmp/factorylink-restore-uploads.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "Could not copy uploads archive into container." }
$restoreUploads = @'
set -eu
stage=/tmp/factorylink-restore-stage; rollback=/tmp/factorylink-pre-restore-uploads.tar.gz
rm -rf "$stage"; mkdir -p "$stage"
tar -tzf /tmp/factorylink-restore-uploads.tar.gz | awk 'BEGIN{bad=0} /^\// || /(^|\/)\.\.($|\/)/ {bad=1} !/^uploads($|\/)/ {bad=1} END{exit bad}'
tar -xzf /tmp/factorylink-restore-uploads.tar.gz -C "$stage"; test -d "$stage/uploads"
find /app/data/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
if cp -a "$stage/uploads/." /app/data/uploads/; then rm -rf "$stage"; else
  find /app/data/uploads -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  tar -xzf "$rollback" -C /app/data; exit 1
fi
rm -f /tmp/factorylink-restore-uploads.tar.gz "$rollback"
'@
docker compose exec -T backend sh -ec $restoreUploads
if ($LASTEXITCODE -ne 0) { throw "Uploads restore failed." }
docker compose stop backend
if ($LASTEXITCODE -ne 0) { throw "Could not stop backend before database restore." }

docker compose cp (Join-Path $backup "database.dump") "db:/tmp/factorylink-restore.dump"
if ($LASTEXITCODE -ne 0) { throw "Could not copy database dump." }
docker compose exec -T db sh -ec 'pg_restore --single-transaction --exit-on-error --clean --if-exists --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/factorylink-restore.dump; rm -f /tmp/factorylink-restore.dump'
if ($LASTEXITCODE -ne 0) { throw "Database restore failed. App services remain stopped." }

docker compose run --rm db-bootstrap
if ($LASTEXITCODE -ne 0) { throw "Runtime DB grants could not be reapplied. App services remain stopped." }
docker compose run --rm --no-deps -e SEED_DEMO_DATA=false migrate
if ($LASTEXITCODE -ne 0) { throw "Database migrations after restore failed. App services remain stopped." }
docker compose up -d backend worker scheduler frontend
if ($LASTEXITCODE -ne 0) { throw "Could not restart application services." }
Write-Host "Restore completed. Verify health, tenant access and document downloads before reopening external traffic." -ForegroundColor Green
Write-Host "Rollback database: $(Join-Path $backup "pre-restore-database-$stamp.dump")"
Write-Host "Rollback uploads:  $(Join-Path $backup "pre-restore-uploads-$stamp.tar.gz")"
