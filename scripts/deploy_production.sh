#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
AUTO_KILL_PORT="${AUTO_KILL_PORT:-1}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
SENSOR1_SCK="${SENSOR1_SCK:-27}"
SENSOR1_DOUT="${SENSOR1_DOUT:-17}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not found."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found. Install Node.js + npm first."
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
PIP_BIN="$ROOT_DIR/.venv/bin/pip3"
RUN_DIR="$ROOT_DIR/run"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUN_DIR/gunicorn.pid"

mkdir -p "$RUN_DIR" "$LOG_DIR"

if command -v lsof >/dev/null 2>&1; then
  existing_pids="$(lsof -tiTCP:"$APP_PORT" -sTCP:LISTEN || true)"
  if [[ -n "$existing_pids" ]]; then
    if [[ "$AUTO_KILL_PORT" == "1" ]]; then
      echo "Port $APP_PORT is in use by PID(s): $existing_pids. Stopping them..."
      kill -9 $existing_pids
    else
      echo "Port $APP_PORT is in use by PID(s): $existing_pids"
      echo "Set APP_PORT to a free port (example: APP_PORT=8001 ./scripts/deploy_production.sh)"
      echo "Or allow auto-kill with AUTO_KILL_PORT=1"
      exit 1
    fi
  fi
fi

"$PIP_BIN" install --upgrade pip
"$PIP_BIN" install -r "$ROOT_DIR/requirements.txt"

cd "$ROOT_DIR/Frontend"
if [[ -f "package-lock.json" ]]; then
  npm ci
else
  npm install
fi
npm run build

cd "$ROOT_DIR/backend"
export DJANGO_DEBUG="0"
export DJANGO_ALLOWED_HOSTS="*"
export SENSOR1_SCK
export SENSOR1_DOUT

"$PYTHON_BIN" manage.py migrate --noinput
"$PYTHON_BIN" manage.py collectstatic --noinput >/dev/null 2>&1 || true

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    kill -TERM "$old_pid" || true
    sleep 1
  fi
fi

"$PYTHON_BIN" -m gunicorn core.wsgi:application \
  --chdir "$ROOT_DIR/backend" \
  --bind "$APP_HOST:$APP_PORT" \
  --workers "$GUNICORN_WORKERS" \
  --threads "$GUNICORN_THREADS" \
  --timeout 120 \
  --access-logfile "$LOG_DIR/gunicorn-access.log" \
  --error-logfile "$LOG_DIR/gunicorn-error.log" \
  --pid "$PID_FILE" \
  --daemon

echo "PipeGuard production server started at http://$APP_HOST:$APP_PORT"
echo "PID file: $PID_FILE"
echo "Logs: $LOG_DIR/gunicorn-access.log and $LOG_DIR/gunicorn-error.log"
