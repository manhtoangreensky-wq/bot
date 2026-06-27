#!/usr/bin/env bash
set -u

BOT_DIR="${BOT_DIR:-/opt/toanaas/bot}"
ENV_FILE="${ENV_FILE:-/etc/toanaas-worker.env}"
SERVICE_NAME="${SERVICE_NAME:-toanaas-worker.service}"

FAIL_COUNT=0
WARN_COUNT=0

ok() { printf 'OK   %s\n' "$*"; }
warn() { WARN_COUNT=$((WARN_COUNT + 1)); printf 'WARN %s\n' "$*" >&2; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf 'FAIL %s\n' "$*" >&2; }

read_env_value() {
  key="$1"
  file="$2"
  [ -f "$file" ] || return 0
  line="$(grep -E "^[[:space:]]*$key=" "$file" | tail -n 1 || true)"
  [ -n "$line" ] || return 0
  value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

mask_secret() {
  secret="$1"
  len=${#secret}
  if [ "$len" -le 8 ]; then
    printf '<configured len=%s>' "$len"
  else
    first="${secret:0:4}"
    last="${secret: -4}"
    printf '%s...%s len=%s' "$first" "$last" "$len"
  fi
}

if command -v python3 >/dev/null 2>&1; then
  ok "python3 found: $(python3 --version 2>&1)"
else
  fail "python3 not found"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg found"
else
  fail "ffmpeg not found"
fi

if [ -d "$BOT_DIR" ]; then
  ok "repo path exists: $BOT_DIR"
else
  fail "repo path missing: $BOT_DIR"
fi

if [ -f "$BOT_DIR/remote_worker.py" ]; then
  ok "remote_worker.py exists"
else
  fail "remote_worker.py missing"
fi

if [ -x "$BOT_DIR/.venv/bin/python" ]; then
  ok "venv python exists"
else
  warn "venv python missing at $BOT_DIR/.venv/bin/python"
fi

if [ -f "$ENV_FILE" ]; then
  ok "env file exists: $ENV_FILE"
  mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo unknown)"
  if [ "$mode" = "600" ]; then
    ok "env file mode is 600"
  else
    warn "env file mode is $mode; expected 600"
  fi
else
  fail "env file missing: $ENV_FILE"
fi

token="$(read_env_value LOCAL_WORKER_TOKEN "$ENV_FILE")"
case "$token" in
  ""|CHANGE_ME|CHANGE_ME_DO_NOT_COMMIT_REAL_TOKEN|PASTE_REAL_TOKEN_ON_SERVER_ONLY)
    fail "LOCAL_WORKER_TOKEN missing or placeholder"
    ;;
  *)
    ok "LOCAL_WORKER_TOKEN configured: $(mask_secret "$token")"
    ;;
esac

bot_api_url="$(read_env_value BOT_API_URL "$ENV_FILE")"
if [ -n "$bot_api_url" ]; then
  ok "BOT_API_URL configured: $bot_api_url"
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 8 "$bot_api_url/runtime" >/dev/null 2>&1; then
      ok "BOT_API_URL /runtime reachable"
    else
      warn "BOT_API_URL /runtime not reachable with curl"
    fi
  else
    warn "curl not found; skipped BOT_API_URL reachability"
  fi
else
  warn "BOT_API_URL missing; remote_worker.py will use its default"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files "$SERVICE_NAME" >/dev/null 2>&1; then
    enabled="$(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || true)"
    active="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
    ok "systemd $SERVICE_NAME enabled=${enabled:-unknown} active=${active:-unknown}"
  else
    warn "systemd service not installed: $SERVICE_NAME"
  fi
else
  warn "systemctl not found; skipped service status"
fi

printf '\nSummary: %s fail(s), %s warning(s)\n' "$FAIL_COUNT" "$WARN_COUNT"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
