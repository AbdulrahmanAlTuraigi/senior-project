#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/run/gunicorn.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill -TERM "$pid"
    echo "Stopped Gunicorn PID $pid"
  else
    echo "PID file exists but process is not running"
  fi
  rm -f "$PID_FILE"
else
  echo "No PID file found at $PID_FILE"
fi
