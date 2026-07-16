#!/usr/bin/env bash
# Start Veritas via Docker Desktop (works when WSL docker CLI is not integrated).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER="${DOCKER:-/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe}"

if ! "$DOCKER" info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then retry."
  exit 1
fi

cd "$ROOT"
export DOCKER_BUILDKIT=1

if [[ "${1:-}" == "--build" ]]; then
  "$DOCKER" compose up --build -d
else
  "$DOCKER" compose up -d
fi

echo ""
echo "Veritas is starting:"
echo "  App:  http://localhost:3000"
echo "  API:  http://localhost:8000/docs"
echo ""
echo "Logs:  $DOCKER compose logs -f"
echo "Stop:  $DOCKER compose down"
