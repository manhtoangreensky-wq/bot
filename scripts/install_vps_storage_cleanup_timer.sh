#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TOANAAS_APP_DIR:-/opt/toanaas-bot}"
CLEANUP_SCRIPT="$APP_DIR/scripts/vps_storage_cleanup.sh"
SERVICE_PATH="/etc/systemd/system/toanaas-storage-cleanup.service"
TIMER_PATH="/etc/systemd/system/toanaas-storage-cleanup.timer"

if [[ "$EUID" -ne 0 ]]; then
  echo "Please run with sudo."
  exit 1
fi

mkdir -p /opt/toanaas-storage/{worker_results,artifacts,tmp,music,subdub,video,cache}
chown -R toanaas:toanaas /opt/toanaas-storage
chmod -R 750 /opt/toanaas-storage

cat > "$SERVICE_PATH" <<SERVICE
[Unit]
Description=TOAN AAS VPS artifact storage cleanup

[Service]
Type=oneshot
User=toanaas
Environment=ARTIFACT_VPS_BASE_DIR=/opt/toanaas-storage
Environment=ARTIFACT_TMP_TTL_HOURS=6
Environment=ARTIFACT_TTL_HOURS=72
Environment=STORAGE_CLEANUP_DRY_RUN=1
ExecStart=$CLEANUP_SCRIPT
SERVICE

cat > "$TIMER_PATH" <<TIMER
[Unit]
Description=Run TOAN AAS storage cleanup hourly

[Timer]
OnBootSec=15min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now toanaas-storage-cleanup.timer
systemctl list-timers toanaas-storage-cleanup.timer

echo "Installed dry-run timer. After verifying logs, set STORAGE_CLEANUP_DRY_RUN=0 in $SERVICE_PATH and run: sudo systemctl daemon-reload"
