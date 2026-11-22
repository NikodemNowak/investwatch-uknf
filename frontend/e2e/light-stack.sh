#!/usr/bin/env bash
# Light stack for the browser tests (CI): the real API and Socket.IO on SQLite, Redis and the
# mock analyzer (Celery eager, in-process), plus `vite preview` of the production build.
# Usage: e2e/light-stack.sh start|stop|restart-api   (needs Redis at $REDIS_URL, `npm run build`)
# E2E_API_PORT / E2E_UI_PORT (default 8000 / 4173) move it off ports another stack holds.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
state="${E2E_STATE_DIR:-${RUNNER_TEMP:-/tmp}/investwatch-e2e}"
mkdir -p "$state"

export APP_DATA_DIR="$repo/data"
export DATABASE_URL="sqlite:///$state/e2e.db"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export CELERY_EAGER=true REALTIME_BACKEND=redis STORAGE_BACKEND=memory AI_MODE=mock
export RENDER_ENABLED=false SEED_LIVE_SOURCES=false REGISTRY_LIVE_SYNC=false
api_port="${E2E_API_PORT:-8000}"
ui_port="${E2E_UI_PORT:-4173}"
export E2E_API_PORT="$api_port"
export CORS_ORIGINS="http://localhost:$ui_port"
venv="$repo/backend/.venv/bin"

wait_for() {
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null "$1" && return 0
    sleep 1
  done
  echo "timeout waiting for $1" >&2
  return 1
}

start_api() {
  (cd "$repo/backend"; nohup "$venv/uvicorn" investwatch.main:app --port "$api_port" --timeout-graceful-shutdown 2 \
    >>"$state/api.log" 2>&1 & echo $! >"$state/api.pid")
  wait_for "http://localhost:$api_port/api/health"
}

stop_pid() {
  if [[ -f "$state/$1.pid" ]]; then
    local pid
    pid="$(cat "$state/$1.pid")"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$state/$1.pid"
  fi
}

case "${1:-}" in
  start)
    rm -f "$state/e2e.db"
    (cd "$repo/backend" && "$venv/python" -m investwatch.seed)
    start_api
    (cd "$repo/frontend"; nohup ./node_modules/.bin/vite preview --port "$ui_port" --strictPort \
      >>"$state/preview.log" 2>&1 & echo $! >"$state/preview.pid")
    wait_for "http://localhost:$ui_port/sprawdz"
    ;;
  restart-api)
    stop_pid api
    start_api
    ;;
  stop)
    stop_pid preview
    stop_pid api
    ;;
  *)
    echo "usage: $0 start|stop|restart-api" >&2
    exit 2
    ;;
esac
