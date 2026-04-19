#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

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
APP_PORT="${APP_PORT:-8000}"
AUTO_KILL_PORT="${AUTO_KILL_PORT:-1}"

if ! command -v lsof >/dev/null 2>&1; then
  echo "warning: lsof not found; cannot pre-check port conflicts"
else
  existing_pids="$(lsof -tiTCP:"$APP_PORT" -sTCP:LISTEN || true)"
  if [[ -n "$existing_pids" ]]; then
    if [[ "$AUTO_KILL_PORT" == "1" ]]; then
      echo "Port $APP_PORT is in use by PID(s): $existing_pids. Stopping them..."
      kill -9 $existing_pids
    else
      echo "Port $APP_PORT is in use by PID(s): $existing_pids"
      echo "Set APP_PORT to a free port (example: APP_PORT=8001 ./scripts/deploy_local.sh)"
      echo "Or allow auto-kill with AUTO_KILL_PORT=1"
      exit 1
    fi
  fi
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt

cd "$ROOT_DIR/Frontend"
if [[ -f "package-lock.json" ]]; then
  npm ci
else
  npm install
fi
npm run build

cd "$ROOT_DIR/backend"
"$PYTHON_BIN" manage.py migrate

# Default wiring is single-sensor SCK=27 DOUT=17; override with env vars if needed.
export SENSOR1_SCK="${SENSOR1_SCK:-17}"
export SENSOR1_DOUT="${SENSOR1_DOUT:-27}"

echo "Starting PipeGuard at http://0.0.0.0:$APP_PORT"
exec "$PYTHON_BIN" manage.py runserver 0.0.0.0:"$APP_PORT"
