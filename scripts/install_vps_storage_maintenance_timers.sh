#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${TOANAAS_APP_DIR:-/opt/toanaas-worker}"
PYTHON_BIN="${TOANAAS_PYTHON:-$APP_DIR/.venv/bin/python}"
UNIT_DIR="/etc/systemd/system"
MODE="${1:---preview-install}"

DAILY_SERVICE="toanaas-storage-daily-cleanup.service"
DAILY_TIMER="toanaas-storage-daily-cleanup.timer"
WEEKLY_SERVICE="toanaas-storage-weekly-cleanup.service"
WEEKLY_TIMER="toanaas-storage-weekly-cleanup.timer"

case "$MODE" in
  --preview-install|--install) ;;
  *)
    echo "Usage: TOANAAS_APP_DIR=/opt/toanaas-worker $0 --preview-install|--install" >&2
    exit 2
    ;;
esac

if [[ ! -d "$APP_DIR" ]]; then
  echo "APP_DIR does not exist: $APP_DIR" >&2
  exit 3
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter is missing or not executable: $PYTHON_BIN" >&2
  exit 4
fi
if [[ ! -f "$APP_DIR/services/storage_maintenance.py" ]]; then
  echo "Storage maintenance entry point is missing: $APP_DIR/services/storage_maintenance.py" >&2
  exit 5
fi

DAILY_SERVICE_CONTENT="[Unit]
Description=TOAN AAS daily backend-local storage cleanup
After=local-fs.target

[Service]
Type=oneshot
User=toanaas
Group=toanaas
WorkingDirectory=$APP_DIR
Environment=TOANAAS_STORAGE_BACKEND=vps
Environment=STORAGE_VPS_ROOT=/opt/toanaas-storage
ExecStart=$PYTHON_BIN -m services.storage_maintenance daily --backend vps --execute
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target"

DAILY_TIMER_CONTENT="[Unit]
Description=Run TOAN AAS daily storage cleanup at noon Vietnam time

[Timer]
OnCalendar=*-*-* 12:00:00 Asia/Ho_Chi_Minh
Persistent=true
Unit=$DAILY_SERVICE

[Install]
WantedBy=timers.target"

WEEKLY_SERVICE_CONTENT="[Unit]
Description=TOAN AAS weekly backend-local backup retention cleanup
After=local-fs.target

[Service]
Type=oneshot
User=toanaas
Group=toanaas
WorkingDirectory=$APP_DIR
Environment=TOANAAS_STORAGE_BACKEND=vps
Environment=STORAGE_VPS_ROOT=/opt/toanaas-storage
ExecStart=$PYTHON_BIN -m services.storage_maintenance weekly --backend vps --keep-backups 3 --execute
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target"

WEEKLY_TIMER_CONTENT="[Unit]
Description=Run TOAN AAS weekly backup cleanup Sunday 03:30 Vietnam time

[Timer]
OnCalendar=Sun *-*-* 03:30:00 Asia/Ho_Chi_Minh
Persistent=true
Unit=$WEEKLY_SERVICE

[Install]
WantedBy=timers.target"

print_contract() {
  echo "TOAN AAS storage maintenance installer"
  echo "mode=$MODE"
  echo "app_dir=$APP_DIR"
  echo "python=$PYTHON_BIN"
  echo "working_directory=$APP_DIR"
  echo "daily_service=$DAILY_SERVICE"
  echo "daily_timer=$DAILY_TIMER schedule=12:00 Asia/Ho_Chi_Minh"
  echo "weekly_service=$WEEKLY_SERVICE"
  echo "weekly_timer=$WEEKLY_TIMER schedule=Sunday 03:30 Asia/Ho_Chi_Minh"
  echo "storage_backend=vps"
  echo "storage_root=/opt/toanaas-storage"
  echo "preview_does_not_enable_start_or_execute=true"
}

if [[ "$MODE" == "--preview-install" ]]; then
  print_contract
  exit 0
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "--install requires root; use sudo." >&2
  exit 6
fi

write_unit() {
  local name="$1"
  local content="$2"
  local temporary
  temporary="$(mktemp "$UNIT_DIR/.${name}.XXXXXX")"
  printf '%s\n' "$content" > "$temporary"
  install -o root -g root -m 0644 "$temporary" "$UNIT_DIR/$name"
  rm -f "$temporary"
}

write_unit "$DAILY_SERVICE" "$DAILY_SERVICE_CONTENT"
write_unit "$DAILY_TIMER" "$DAILY_TIMER_CONTENT"
write_unit "$WEEKLY_SERVICE" "$WEEKLY_SERVICE_CONTENT"
write_unit "$WEEKLY_TIMER" "$WEEKLY_TIMER_CONTENT"

systemctl daemon-reload
systemctl enable "$DAILY_TIMER" "$WEEKLY_TIMER"
print_contract
echo "installed=true"
echo "execute_cleanup_started=false"
