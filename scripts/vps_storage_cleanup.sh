#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TOANAAS_APP_DIR:-/opt/toanaas-worker}"
PYTHON_BIN="${TOANAAS_PYTHON:-$APP_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Storage maintenance Python is missing: $PYTHON_BIN" >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/services/storage_maintenance.py" ]]; then
  echo "Storage maintenance runtime is missing under $APP_DIR" >&2
  exit 1
fi
cd "$APP_DIR"

if [[ "${STORAGE_CLEANUP_DRY_RUN:-1}" == "1" || "${STORAGE_CLEANUP_DRY_RUN:-1}" == "true" ]]; then
  exec "$PYTHON_BIN" -m services.storage_maintenance daily --backend vps --preview
fi
exec "$PYTHON_BIN" -m services.storage_maintenance daily --backend vps --execute
