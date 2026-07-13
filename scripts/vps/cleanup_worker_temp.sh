#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---dry-run}"
ROOT="${WORKER_TMP_DIR:-/tmp}"
APP_DIR="${TOANAAS_APP_DIR:-/opt/toanaas-worker}"
PYTHON_BIN="${TOANAAS_PYTHON:-$APP_DIR/.venv/bin/python}"

if [[ "$MODE" != "--dry-run" && "$MODE" != "--apply" ]]; then
  echo "Usage: WORKER_TMP_DIR=/tmp $0 --dry-run|--apply" >&2
  exit 2
fi

case "$ROOT" in
  /tmp|/tmp/*|/var/tmp|/var/tmp/*) ;;
  *)
    echo "Refusing unsafe temp root: $ROOT" >&2
    exit 3
    ;;
esac

if [[ ! -d "$ROOT" ]]; then
  echo "Temp root not found: $ROOT"
  exit 0
fi
if [[ ! -x "$PYTHON_BIN" || ! -f "$APP_DIR/services/storage_maintenance.py" ]]; then
  echo "Storage maintenance runtime is missing under $APP_DIR" >&2
  exit 4
fi
cd "$APP_DIR"

export STORAGE_EXTRA_TEMP_ROOTS="$ROOT"
if [[ "$MODE" == "--apply" ]]; then
  exec "$PYTHON_BIN" -m services.storage_maintenance daily --backend vps --execute
fi
exec "$PYTHON_BIN" -m services.storage_maintenance daily --backend vps --preview
