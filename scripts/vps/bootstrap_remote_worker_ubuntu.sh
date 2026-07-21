#!/usr/bin/env bash
set -euo pipefail

TOANAAS_ROOT="${TOANAAS_ROOT:-/opt/toanaas}"
BOT_DIR="${BOT_DIR:-$TOANAAS_ROOT/bot}"
TMP_DIR="${WORKER_TMP_DIR:-$TOANAAS_ROOT/tmp}"
REPO_URL="${REPO_URL:-https://github.com/manhtoangreensky-wq/bot.git}"
SWAP_SIZE="${SWAP_SIZE:-4G}"
RUN_APT_UPGRADE="${RUN_APT_UPGRADE:-0}"
SETUP_VENV="${SETUP_VENV:-1}"

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

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ok "Detected ${PRETTY_NAME:-Linux}" ;;
    *) warn "This script is intended for Ubuntu; detected ${PRETTY_NAME:-unknown}." ;;
  esac
fi

case "$REPO_URL" in
  *://*@*|git@*)
    fail "REPO_URL must not contain embedded credentials or SSH credentials."
    ;;
esac

command -v apt-get >/dev/null 2>&1 || fail "apt-get not found; use Ubuntu/Debian."

ok "Installing base packages"
$SUDO apt-get update
if [ "$RUN_APT_UPGRADE" = "1" ]; then
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get upgrade -y
else
  warn "Skipping apt upgrade. Set RUN_APT_UPGRADE=1 to run it."
fi
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y git curl python3 python3-venv python3-pip ffmpeg sqlite3 nano

ok "Creating directories"
$SUDO mkdir -p "$TOANAAS_ROOT" "$TMP_DIR"

if swapon --show --noheadings | grep -q .; then
  ok "Swap already active"
else
  if [ -e /swapfile ]; then
    warn "/swapfile already exists; attempting to enable existing swapfile without overwriting it"
    $SUDO chmod 600 /swapfile || true
    $SUDO swapon /swapfile || warn "Could not enable existing /swapfile"
  else
    ok "Creating /swapfile size $SWAP_SIZE"
    $SUDO fallocate -l "$SWAP_SIZE" /swapfile
    $SUDO chmod 600 /swapfile
    $SUDO mkswap /swapfile
    $SUDO swapon /swapfile
  fi
fi

if ! grep -qsE '^/swapfile[[:space:]]' /etc/fstab; then
  ok "Adding /swapfile to /etc/fstab"
  printf '%s\n' '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
else
  ok "/etc/fstab already contains /swapfile"
fi

if [ -d "$BOT_DIR/.git" ]; then
  ok "Repo already exists at $BOT_DIR; not overwriting"
elif [ -e "$BOT_DIR" ]; then
  fail "$BOT_DIR exists but is not a git repo. Move it manually before cloning."
else
  ok "Cloning public repo to $BOT_DIR"
  $SUDO git clone "$REPO_URL" "$BOT_DIR"
fi

if [ "$SETUP_VENV" = "1" ]; then
  if [ ! -x "$BOT_DIR/.venv/bin/python" ]; then
    ok "Creating Python virtualenv"
    $SUDO python3 -m venv "$BOT_DIR/.venv"
  else
    ok "Virtualenv already exists"
  fi
  ok "Installing Python requirements"
  $SUDO "$BOT_DIR/.venv/bin/python" -m pip install -U pip
  if [ -f "$BOT_DIR/requirements.txt" ]; then
    $SUDO "$BOT_DIR/.venv/bin/python" -m pip install -r "$BOT_DIR/requirements.txt"
  else
    warn "requirements.txt not found at $BOT_DIR"
  fi
else
  warn "Skipping virtualenv setup because SETUP_VENV=$SETUP_VENV"
fi

cat <<'NEXT_STEPS'

Next manual steps:
1. Copy deploy/env/toanaas-worker.env.example to /etc/toanaas-worker.env.
2. Paste the real LOCAL_WORKER_TOKEN only on the VPS.
3. Run: chmod 600 /etc/toanaas-worker.env
4. Run: bash /opt/toanaas/bot/scripts/vps/install_remote_worker_service.sh
5. Run: bash /opt/toanaas/bot/scripts/vps/remote_worker_doctor.sh
6. Start only after /tool_test_remote_worker_api --fake-job --no-charge passes.

This bootstrap script did not start the worker service.
NEXT_STEPS
