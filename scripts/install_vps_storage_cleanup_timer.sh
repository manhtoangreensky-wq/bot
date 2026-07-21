#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TOANAAS_APP_DIR:-/opt/toanaas-worker}"
INSTALLER="$APP_DIR/scripts/install_vps_storage_maintenance_timers.sh"
if [[ ! -f "$INSTALLER" ]]; then
  echo "Storage maintenance installer is missing: $INSTALLER" >&2
  exit 1
fi
if [[ "$#" -eq 0 ]]; then
  set -- --preview-install
fi
exec bash "$INSTALLER" "$@"
