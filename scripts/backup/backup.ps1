param([string]$BackupRoot = ".backups", [int]$RetentionDays = 30)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "../..")
if ($RetentionDays -lt 1) { throw "RetentionDays must be positive." }
if (-not (Test-Path ".env")) { throw "Missing .env. Copy .env.example to .env first." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI not found." }
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$root = [IO.Path]::GetFullPath($BackupRoot); New-Item -ItemType Directory -Force -Path $root | Out-Null
$target = Join-Path $root "factorylink-$stamp"; New-Item -ItemType Directory -Path $target | Out-Null
try {
    docker compose exec -T db sh -ec 'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/factorylink-backup.dump'
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
    docker compose cp "db:/tmp/factorylink-backup.dump" (Join-Path $target "database.dump")
    if ($LASTEXITCODE -ne 0) { throw "Could not copy database dump." }
    docker compose exec -T db rm -f /tmp/factorylink-backup.dump | Out-Null
    docker compose exec -T backend sh -ec 'tar -C /app/data -czf /tmp/factorylink-uploads.tar.gz uploads'
    if ($LASTEXITCODE -ne 0) { throw "Uploads archive failed." }
    docker compose cp "backend:/tmp/factorylink-uploads.tar.gz" (Join-Path $target "uploads.tar.gz")
    if ($LASTEXITCODE -ne 0) { throw "Could not copy uploads archive." }
    docker compose exec -T backend rm -f /tmp/factorylink-uploads.tar.gz | Out-Null
    $dbHash = (Get-FileHash (Join-Path $target "database.dump") -Algorithm SHA256).Hash.ToLowerInvariant()
    $uploadHash = (Get-FileHash (Join-Path $target "uploads.tar.gz") -Algorithm SHA256).Hash.ToLowerInvariant()
    @("$dbHash  database.dump", "$uploadHash  uploads.tar.gz") | Set-Content -Encoding ascii (Join-Path $target "SHA256SUMS")
    @("created_at_utc=$stamp", "format=PostgreSQL custom dump + uploads tar.gz") | Set-Content -Encoding ascii (Join-Path $target "BACKUP_INFO.txt")
    Get-ChildItem $root -Directory -Filter "factorylink-*" | Where-Object { $_.LastWriteTimeUtc -lt (Get-Date).ToUniversalTime().AddDays(-$RetentionDays) } | Remove-Item -Recurse -Force
    Write-Host "Backup created: $target" -ForegroundColor Green
} catch { Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue; throw }
