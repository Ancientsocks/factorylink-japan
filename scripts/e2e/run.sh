#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python -m pip install -r backend/requirements.txt -r e2e/requirements.txt
(cd frontend && npm install --no-audit --no-fund)
python -m playwright install chromium
python -m pytest -q e2e
