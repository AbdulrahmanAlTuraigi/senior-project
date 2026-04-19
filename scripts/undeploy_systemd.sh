#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="pipeguard"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if sudo systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
  sudo systemctl disable --now "$SERVICE_NAME" || true
fi

if [[ -f "$SERVICE_FILE" ]]; then
  sudo rm -f "$SERVICE_FILE"
fi

sudo systemctl daemon-reload

echo "Removed systemd deployment for ${SERVICE_NAME}."
