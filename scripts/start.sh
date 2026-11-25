#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. These values are for local evaluation only."
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI not found. Install Docker Engine and the Compose plugin." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker Engine is not running. Start Docker Desktop/Engine, then rerun ./scripts/start.sh." >&2
  exit 1
fi

# Plain progress keeps dependency-install errors visible in terminal output.
docker compose --progress plain up --build -d
PORT="$(awk -F= '$1 == "APP_PORT" { print $2; exit }' .env | tr -d '\r')"
PORT="${PORT:-8080}"
URL="http://localhost:${PORT}"
echo "Waiting for FactoryLink at ${URL} (up to 10 minutes for initial ClamAV signature loading) ..."
for _ in $(seq 1 300); do
  if curl --silent --fail --output /dev/null "${URL}/health/ready"; then
    docker compose ps
    echo "FactoryLink is ready: ${URL}"
    echo "API docs: ${URL}/docs"
    exit 0
  fi
  sleep 2
done

echo "FactoryLink did not become healthy. Recent logs:" >&2
docker compose logs --tail=80 >&2
exit 1
