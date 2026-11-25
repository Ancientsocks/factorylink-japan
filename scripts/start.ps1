$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. These values are for local evaluation only." -ForegroundColor Yellow
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop, then reopen PowerShell."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine is not running. Open Docker Desktop, wait for 'Engine running', then rerun .\scripts\start.ps1."
}

# Plain progress preserves the pip/npm error lines that Docker's TTY progress can hide.
docker compose --progress plain up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to start. Review the Docker Desktop engine and build output."
}

$portLine = Get-Content ".env" | Where-Object { $_ -match '^APP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { ($portLine -split '=', 2)[1].Trim() } else { "8080" }
$url = "http://localhost:$port"
Write-Host "Waiting for FactoryLink at $url (up to 10 minutes for initial ClamAV signature loading) ..." -ForegroundColor Cyan
$ready = $false
for ($attempt = 0; $attempt -lt 300; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$url/health/ready" -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

docker compose ps
if (-not $ready) {
    Write-Host "FactoryLink did not become reachable. Recent logs:" -ForegroundColor Red
    docker compose logs --tail=80
    throw "Startup timed out. Check the service logs above and run 'docker compose ps'."
}
Write-Host "FactoryLink is ready: $url" -ForegroundColor Green
Write-Host "API docs: $url/docs" -ForegroundColor Green
