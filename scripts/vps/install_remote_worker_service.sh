#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/opt/toanaas/bot}"
ENV_FILE="${ENV_FILE:-/etc/toanaas-worker.env}"
SERVICE_NAME="${SERVICE_NAME:-toanaas-worker.service}"
SERVICE_DEST="${SERVICE_DEST:-/etc/systemd/system/$SERVICE_NAME}"
RUN_START="${RUN_START:-0}"

ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*" >&2; }
fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    fail "Run as root or install sudo."
  fi
fi

[ -d "$BOT_DIR" ] || fail "$BOT_DIR does not exist."
[ -f "$BOT_DIR/remote_worker.py" ] || fail "$BOT_DIR/remote_worker.py does not exist."
[ -x "$BOT_DIR/.venv/bin/python" ] || fail "$BOT_DIR/.venv/bin/python does not exist or is not executable."
[ -f "$ENV_FILE" ] || fail "$ENV_FILE does not exist."

SERVICE_SRC="$BOT_DIR/deploy/systemd/toanaas-remote-worker.service.example"
[ -f "$SERVICE_SRC" ] || fail "$SERVICE_SRC does not exist."

token_line="$(grep -E '^[[:space:]]*LOCAL_WORKER_TOKEN=' "$ENV_FILE" | tail -n 1 || true)"
[ -n "$token_line" ] || fail "LOCAL_WORKER_TOKEN is missing from $ENV_FILE."
token_value="${token_line#*=}"
token_value="${token_value%\"}"
token_value="${token_value#\"}"
token_value="${token_value%\'}"
token_value="${token_value#\'}"

case "$token_value" in
  ""|CHANGE_ME|CHANGE_ME_DO_NOT_COMMIT_REAL_TOKEN|PASTE_REAL_TOKEN_ON_SERVER_ONLY)
    fail "LOCAL_WORKER_TOKEN still looks like a placeholder."
    ;;
esac

if [ "$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo unknown)" != "600" ]; then
  warn "$ENV_FILE is not chmod 600; fixing permissions"
  $SUDO chmod 600 "$ENV_FILE"
fi

ok "Installing systemd service to $SERVICE_DEST"
$SUDO cp "$SERVICE_SRC" "$SERVICE_DEST"
$SUDO chmod 644 "$SERVICE_DEST"
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME"

if [ "$RUN_START" = "1" ]; then
  ok "RUN_START=1 set; starting $SERVICE_NAME"
  $SUDO systemctl start "$SERVICE_NAME"
else
  warn "Service enabled but not started."
  warn "After dry-run passes, start with: sudo systemctl start $SERVICE_NAME"
fi

ok "Done"
