#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

APP_PORT="${APP_PORT:-8000}"
APP_URL="http://127.0.0.1:${APP_PORT}"
TUNNEL_PROTOCOL="${TUNNEL_PROTOCOL:-http2}"
RUN_DIR="$ROOT_DIR/run"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUN_DIR/cloudflared.pid"
LOG_FILE="$LOG_DIR/public-tunnel.log"

mkdir -p "$RUN_DIR" "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    kill -TERM "$old_pid" || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Kill any stray cloudflared quick-tunnel process.
pkill -f "cloudflared tunnel --url" || true

nohup cloudflared tunnel --url "$APP_URL" --protocol "$TUNNEL_PROTOCOL" --no-autoupdate >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "Starting public tunnel for $APP_URL ..."

for _ in $(seq 1 40); do
  if grep -qE 'https://[a-z0-9.-]+\.trycloudflare\.com' "$LOG_FILE"; then
    tunnel_url="$(grep -Eo 'https://[a-z0-9.-]+\.trycloudflare\.com' "$LOG_FILE" | tail -n 1)"
    echo "Public URL: $tunnel_url"
    echo "Tunnel PID: $(cat "$PID_FILE")"
    echo "Log: $LOG_FILE"
    exit 0
  fi
  sleep 1
done

echo "Tunnel started but URL not detected yet. Check: $LOG_FILE"
exit 1
