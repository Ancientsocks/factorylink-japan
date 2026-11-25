$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $Root
python -m pip install -r backend/requirements.txt -r e2e/requirements.txt
Push-Location frontend
try { npm install --no-audit --no-fund } finally { Pop-Location }
python -m playwright install chromium
python -m pytest -q e2e
