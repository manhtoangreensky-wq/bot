#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/opt/toanaas/bot}"
ENV_FILE="${ENV_FILE:-/etc/toanaas-worker.env}"
SERVICE_NAME="${SERVICE_NAME:-all}"
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

service_source() {
  case "$1" in
    toanaas-worker.service)
      printf '%s\n' "$BOT_DIR/deploy/systemd/toanaas-remote-worker.service.example"
      ;;
    toanaas-worker-admin-canary.service|toanaas-worker-owner-product-video.service|toanaas-worker-product-video.service|toanaas-worker-admin-video.service)
      printf '%s\n' "$BOT_DIR/deploy/systemd/$1"
      ;;
    *)
      fail "Unknown SERVICE_NAME=$1"
      ;;
  esac
}

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

if [ "$SERVICE_NAME" = "all" ]; then
  SERVICES=(
    "toanaas-worker-admin-canary.service"
    "toanaas-worker-owner-product-video.service"
    "toanaas-worker-product-video.service"
    "toanaas-worker-admin-video.service"
  )
else
  SERVICES=("$SERVICE_NAME")
fi

for service in "${SERVICES[@]}"; do
  SERVICE_SRC="$(service_source "$service")"
  [ -f "$SERVICE_SRC" ] || fail "$SERVICE_SRC does not exist."
  SERVICE_DEST="/etc/systemd/system/$service"
  ok "Installing systemd service to $SERVICE_DEST"
  $SUDO cp "$SERVICE_SRC" "$SERVICE_DEST"
  $SUDO chmod 644 "$SERVICE_DEST"
done

$SUDO systemctl daemon-reload
for service in "${SERVICES[@]}"; do
  $SUDO systemctl enable "$service"
done

if [ "$RUN_START" = "1" ]; then
  ok "RUN_START=1 set; starting installed services"
  for service in "${SERVICES[@]}"; do
    $SUDO systemctl start "$service"
  done
else
  warn "Services enabled but not started."
  warn "After dry-run passes, start selected lanes explicitly with: sudo systemctl start toanaas-worker-owner-product-video"
fi

ok "Done"
