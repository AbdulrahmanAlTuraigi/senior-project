#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="pipeguard"
APP_PORT="${APP_PORT:-8000}"

echo "=== systemctl status ==="
sudo systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "=== listener ==="
ss -lntp | grep ":$APP_PORT" || true

echo "=== health ==="
curl -sS "http://127.0.0.1:$APP_PORT/api/system/status" || true
echo
