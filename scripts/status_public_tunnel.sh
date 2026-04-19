#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/run/cloudflared.pid"
LOG_FILE="$ROOT_DIR/logs/public-tunnel.log"

echo "=== Tunnel PID ==="
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" || true)"
  echo "PID file: $PID_FILE"
  echo "PID: ${pid:-<empty>}"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "Process state: running"
  else
    echo "Process state: not running"
  fi
else
  echo "No PID file"
fi

echo "=== Public URL ==="
if [[ -f "$LOG_FILE" ]]; then
  grep -Eo 'https://[a-z0-9.-]+\.trycloudflare\.com' "$LOG_FILE" | tail -n 1 || echo "URL not found yet"
else
  echo "No log file"
fi
