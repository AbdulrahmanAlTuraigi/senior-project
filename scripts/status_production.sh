#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_PORT="${APP_PORT:-8000}"
PID_FILE="$ROOT_DIR/run/gunicorn.pid"

echo "=== Port Listener ==="
ss -lntp | grep ":$APP_PORT" || echo "No process listening on :$APP_PORT"

echo "=== PID File ==="
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" || true)"
  echo "PID file: $PID_FILE"
  echo "PID: ${pid:-<empty>}"
else
  echo "PID file not found: $PID_FILE"
fi

echo "=== Health ==="
curl -sS "http://127.0.0.1:$APP_PORT/api/system/status" || echo "Health endpoint unreachable"

echo
