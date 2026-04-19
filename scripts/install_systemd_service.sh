#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="pipeguard"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
SENSOR1_SCK="${SENSOR1_SCK:-27}"
SENSOR1_DOUT="${SENSOR1_DOUT:-17}"

if command -v lsof >/dev/null 2>&1; then
  existing_pids="$(lsof -tiTCP:"$APP_PORT" -sTCP:LISTEN || true)"
  if [[ -n "$existing_pids" ]]; then
    echo "Port $APP_PORT is currently in use by PID(s): $existing_pids. Stopping them..."
    kill -9 $existing_pids || true
  fi
fi

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Virtualenv python not found at $ROOT_DIR/.venv/bin/python"
  echo "Run ./scripts/deploy_production.sh once first."
  exit 1
fi

cat <<EOF | sudo tee "$SERVICE_FILE" >/dev/null
[Unit]
Description=PipeGuard Django + Gunicorn Service
After=network.target

[Service]
Type=simple
User=test
Group=test
WorkingDirectory=$ROOT_DIR
Environment=DJANGO_DEBUG=0
Environment=DJANGO_ALLOWED_HOSTS=*
Environment=SENSOR1_SCK=$SENSOR1_SCK
Environment=SENSOR1_DOUT=$SENSOR1_DOUT
ExecStart=$ROOT_DIR/.venv/bin/python -m gunicorn core.wsgi:application --chdir $ROOT_DIR/backend --bind $APP_HOST:$APP_PORT --workers $GUNICORN_WORKERS --threads $GUNICORN_THREADS --timeout 120 --access-logfile $ROOT_DIR/logs/gunicorn-access.log --error-logfile $ROOT_DIR/logs/gunicorn-error.log
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Installed and started systemd service: $SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,20p'
